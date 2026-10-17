//! HTTP wrapper exposing one iroh-docs replica through the HttpKV contract of bench/adapters.py:
//!   GET /kv/:key  PUT /kv/:key  POST /bulk  POST /query {criteria}  GET /snapshot  GET /ticket
//! The first node (no TICKET env var) creates the document and serves a write ticket at GET /ticket;
//! every other node starts with TICKET=<ticket> and joins it. Storage is persistent under DATA_DIR.
//! Reads use the latest entry per key across authors (iroh-docs resolves same author+key by timestamp).
use std::{str::FromStr, sync::Arc};

use anyhow::Result;
use axum::{
    extract::{DefaultBodyLimit, Path, State},
    http::StatusCode,
    routing::{get, post},
    Json, Router,
};
use iroh::{endpoint::presets, protocol::Router as IrohRouter, Endpoint};
use iroh_blobs::{store::fs::FsStore, BlobsProtocol};
use iroh_docs::{
    api::{protocol::{AddrInfoOptions, ShareMode}, Doc},
    protocol::Docs,
    store::Query,
    AuthorId, DocTicket,
};
use iroh_gossip::net::Gossip;
use n0_future::{BufferedStreamExt, StreamExt};
use serde_json::Value;

struct App {
    doc: Doc,
    author: AuthorId,
    blobs: iroh_blobs::api::Store,
    ticket: String,
}
type S = State<Arc<App>>;

async fn read_entry(app: &App, e: &iroh_docs::Entry) -> Option<Value> {
    let bytes = app.blobs.get_bytes(e.content_hash()).await.ok()?;   // content not yet downloaded -> None
    serde_json::from_slice(&bytes).ok()
}

// Client-side evaluation over every key (iroh-docs has no query language). Contents are read SCAN_PARALLEL at a
// time instead of one after another, and a document is parsed only if its stored JSON text contains every
// criterion as serde_json writes it ("region":"eu-west"); candidates are then checked field by field, so the
// result is exactly the filter's. Reading and parsing 10^5 documents one by one took longer than the 10 s
// operation timeout in the pilot, so every WO query failed.
const SCAN_PARALLEL: usize = 64;

fn contains(hay: &[u8], needle: &[u8]) -> bool {
    needle.is_empty() || hay.windows(needle.len()).any(|w| w == needle)
}

async fn scan(app: &App, crit: &serde_json::Map<String, Value>) -> Vec<Value> {
    let needles: Vec<Vec<u8>> = crit.iter()
        .filter(|(_, v)| !v.is_object() && !v.is_array())
        .map(|(k, v)| format!("{}:{}", Value::String(k.clone()), v).into_bytes()).collect();
    let Ok(stream) = app.doc.get_many(Query::single_latest_per_key()).await else { return Vec::new() };
    let entries: Vec<_> = stream.collect().await;
    let blobs = app.blobs.clone();
    let needles = &needles;
    n0_future::stream::iter(entries.into_iter().flatten())
        .map(|e| { let blobs = blobs.clone(); async move { blobs.get_bytes(e.content_hash()).await.ok() } })
        .buffered_unordered(SCAN_PARALLEL)
        .filter_map(|b| {
            let b = b?;                                              // content not yet downloaded -> skipped
            if !needles.iter().all(|n| contains(&b, n)) { return None; }
            let d: Value = serde_json::from_slice(&b).ok()?;
            crit.iter().all(|(k, v)| d.get(k) == Some(v)).then_some(d)
        })
        .collect().await
}

async fn all_docs(app: &App) -> Vec<Value> { scan(app, &serde_json::Map::new()).await }

async fn get_kv(State(app): S, Path(key): Path<String>) -> Result<Json<Value>, StatusCode> {
    let e = app.doc.get_one(Query::single_latest_per_key().key_exact(key.as_bytes()))
        .await.map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?.ok_or(StatusCode::NOT_FOUND)?;
    read_entry(&app, &e).await.map(Json).ok_or(StatusCode::NOT_FOUND)
}

async fn put_kv(State(app): S, Path(key): Path<String>, Json(v): Json<Value>) -> Result<Json<Value>, StatusCode> {
    app.doc.set_bytes(app.author, key.into_bytes(), serde_json::to_vec(&v).unwrap())
        .await.map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;
    Ok(Json(serde_json::json!({"ok": 1})))
}

async fn bulk(State(app): S, Json(docs): Json<Vec<Value>>) -> Result<Json<Value>, StatusCode> {
    for d in &docs {
        let key = d.get("_id").and_then(|k| k.as_str()).ok_or(StatusCode::BAD_REQUEST)?.to_string();
        app.doc.set_bytes(app.author, key.into_bytes(), serde_json::to_vec(d).unwrap())
            .await.map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;
    }
    Ok(Json(serde_json::json!({"ok": docs.len()})))
}

async fn query(State(app): S, Json(c): Json<Value>) -> Json<Value> {
    // no query language: client-side filtering over all keys (as an application would)
    let crit = c.as_object().cloned().unwrap_or_default();
    Json(serde_json::json!({ "results": scan(&app, &crit).await }))
}

async fn snapshot(State(app): S) -> Json<Value> { Json(Value::Array(all_docs(&app).await)) }
async fn get_ticket(State(app): S) -> String { app.ticket.clone() }
async fn health() -> &'static str { "ok" }   // answers even when the docs actor is blocked

#[tokio::main]
async fn main() -> Result<()> {
    // Diagnostics: RUST_LOG=iroh_docs=debug,iroh_gossip=debug shows where a stalled write waits (default: warn).
    tracing_subscriber::fmt()
        .with_env_filter(tracing_subscriber::EnvFilter::try_from_default_env()
            .unwrap_or_else(|_| tracing_subscriber::EnvFilter::new("warn")))
        .init();
    let dir = std::path::PathBuf::from(std::env::var("DATA_DIR").unwrap_or_else(|_| "iroh-data".into()));
    let port: u16 = std::env::var("PORT").ok().and_then(|p| p.parse().ok()).unwrap_or(7006);
    // Minimal preset: no public relays or discovery (isolated testbed); peers are reached via ticket addresses.
    std::fs::create_dir_all(dir.join("docs"))?;
    let endpoint = Endpoint::bind(presets::Minimal).await?;
    let store = FsStore::load(dir.join("blobs")).await?;
    let blobs: iroh_blobs::api::Store = (*store).clone();
    let gossip = Gossip::builder().spawn(endpoint.clone());
    let docs = Docs::persistent(dir.join("docs")).spawn(endpoint.clone(), blobs.clone(), gossip.clone()).await?;
    let _router = IrohRouter::builder(endpoint.clone())
        .accept(iroh_blobs::ALPN, BlobsProtocol::new(&blobs, None))
        .accept(iroh_gossip::ALPN, gossip)
        .accept(iroh_docs::ALPN, docs.clone())
        .spawn();
    let api = docs.api().clone();
    let author = api.author_default().await?;
    let doc = match std::env::var("TICKET") {
        Ok(t) if !t.is_empty() => api.import(DocTicket::from_str(&t)?).await?,
        _ => api.create().await?,
    };
    let ticket = doc.share(ShareMode::Write, AddrInfoOptions::Addresses).await?.to_string();
    let app = Arc::new(App { doc, author, blobs, ticket });
    let http = Router::new()
        .route("/kv/{key}", get(get_kv).put(put_kv))
        .route("/bulk", post(bulk))
        .route("/query", post(query))
        .route("/snapshot", get(snapshot))
        .route("/ticket", get(get_ticket))
        .route("/health", get(health))
        .layer(DefaultBodyLimit::max(64 * 1024 * 1024))   // bulk loads of 64 KB documents
        .with_state(app);
    let lis = tokio::net::TcpListener::bind(("0.0.0.0", port)).await?;
    println!("iroh wrapper on {port}");
    axum::serve(lis, http).await?;
    Ok(())
}
