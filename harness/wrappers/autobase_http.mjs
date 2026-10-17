// HTTP wrapper exposing an Autobase (multi-writer Hypercore) with a Hyperbee view through the
// HttpKV contract of bench/adapters.py:
//   GET /kv/:key  PUT /kv/:key  POST /bulk  POST /query {criteria}  GET /snapshot
//   GET /admin/key (this node's writer key)   POST /admin/add-writer {key}  (run on the bootstrap node)
// npm i autobase@7.28.2 corestore hyperbee hyperswarm express   (record versions in the Baselines sheet)
// The first node starts without BOOTSTRAP and prints the base key; the others start with
// BOOTSTRAP=<base key>. The deploy script then calls /admin/add-writer on the first node for each
// other node's /admin/key, so every node is a writer and an indexer.
// On the isolated testbed, Hyperswarm must use a local DHT bootstrap: DHT_BOOTSTRAP=host:port
// (e.g. `npx hyperdht --bootstrap --host 10.0.1.11 --port 49737` on the cloud host), or direct TCP
// replication with REPL_PORT and PEERS (see below).
import express from 'express'
import Corestore from 'corestore'
import Autobase from 'autobase'
import Hyperbee from 'hyperbee'
import Hyperswarm from 'hyperswarm'
import net from 'net'

const PORT = Number(process.env.PORT || 7005)
const store = new Corestore(process.env.DATA_DIR || 'autobase-data')
const bootstrapKey = process.env.BOOTSTRAP ? Buffer.from(process.env.BOOTSTRAP, 'hex') : null

function open (store) {
  return new Hyperbee(store.get('view'), { keyEncoding: 'utf-8', valueEncoding: 'json', extension: false })
}
// apply: the deterministic, causally ordered stream of all writers' blocks is folded into the view.
// Concurrent puts to the same key resolve to the one linearized last (application-defined order).
async function apply (nodes, view, host) {
  for (const { value } of nodes) {
    if (value.addWriter) { await host.addWriter(Buffer.from(value.addWriter, 'hex'), { indexer: value.indexer !== false }); continue }
    if (value.put) await view.put(value.put.key, value.put.doc)
  }
}
const base = new Autobase(store, bootstrapKey, { open, apply, valueEncoding: 'json' })
await base.ready()

// Peer connectivity. Default: Hyperswarm on the base's discovery key (DHT_BOOTSTRAP for a private DHT).
// Alternative for isolated testbeds where UDP hole punching is unavailable: REPL_PORT + PEERS=host:port,...
// opens direct TCP replication streams between the listed nodes (same Corestore replication protocol).
if (process.env.PEERS !== undefined) {
  const REPL_PORT = Number(process.env.REPL_PORT || 7305)
  const pipe = (isInitiator, sock) => { const r = store.replicate(isInitiator); r.on('error', () => {}); sock.on('error', () => {}); r.pipe(sock).pipe(r) }
  net.createServer(sock => pipe(false, sock)).listen(REPL_PORT)
  const dial = (host, port) => {
    const sock = net.connect(port, host)
    pipe(true, sock)
    sock.on('close', () => setTimeout(() => dial(host, port), 1000))   // reconnect after partitions
  }
  for (const p of process.env.PEERS.split(',').filter(Boolean)) { const [h, pt] = p.split(':'); dial(h, Number(pt)) }
} else {
  const dht = process.env.DHT_BOOTSTRAP ? { bootstrap: process.env.DHT_BOOTSTRAP.split(',').map(s => { const [host, port] = s.split(':'); return { host, port: Number(port) } }) } : {}
  const swarm = new Hyperswarm(dht)
  swarm.on('connection', conn => store.replicate(conn))
  swarm.join(base.discoveryKey)
}

// A failed request must not stop the node. Express 4 does not catch rejected async handlers, and Node exits on
// an unhandled rejection, so one failing append or read used to kill the wrapper for the rest of the block.
process.on('unhandledRejection', e => console.error('unhandled rejection:', e && e.stack || e))
process.on('uncaughtException', e => console.error('uncaught exception:', e && e.stack || e))
const handle = fn => async (req, res) => {
  try { await fn(req, res) } catch (e) { console.error(req.method, req.path, e && e.message); if (!res.headersSent) res.status(500).send(String(e && e.message || e)) }
}

// The view is brought up to date in the background, as a running application would do, instead of a full
// base.update() (pull from every peer and re-linearize) inside every read: under a write load each read waited
// for that, and reads queued for over a minute. Reads and queries use the local view, as in the other systems;
// /snapshot (replica comparison) still forces an update.
const REFRESH_MS = Number(process.env.REFRESH_MS || 100)
let refreshing = false
setInterval(() => {
  if (refreshing) return
  refreshing = true
  base.update().catch(e => console.error('background update:', e && e.message)).finally(() => { refreshing = false })
}, REFRESH_MS)

const put = async (key, doc) => base.append({ put: { key, doc } })
// Scans keep only matching documents: collecting all 10^5 values first and filtering afterwards held ~0.5 GB per
// scan in memory, and several scans in flight ran the edge nodes out of memory in the pilot.
const scan = async (range = {}, fresh = false, keep = () => true) => {
  if (fresh) await base.update()
  const out = []
  for await (const { value } of base.view.createReadStream(range)) if (keep(value)) out.push(value)
  return out
}

const app = express(); app.use(express.json({ limit: '64mb' }))
app.get('/kv/:key', handle(async (req, res) => {
  const n = await base.view.get(req.params.key)
  n ? res.json(n.value) : res.status(404).end()
}))
app.put('/kv/:key', handle(async (req, res) => { await put(req.params.key, req.body); res.json({ ok: 1 }) }))
// Bulk load: one append per batch of BULK_BATCH documents (Autobase appends an array as one batch of blocks),
// instead of one append per document; the view is the same.
const BULK_BATCH = Number(process.env.BULK_BATCH || 500)
app.post('/bulk', handle(async (req, res) => {
  const docs = req.body
  for (let i = 0; i < docs.length; i += BULK_BATCH) {
    await base.append(docs.slice(i, i + BULK_BATCH).map(d => ({ put: { key: d._id, doc: d } })))
  }
  res.json({ ok: docs.length })
}))
// At most SCAN_CONCURRENCY scans run at a time; the others wait their turn (the wait is part of their latency),
// and a scan whose client has already given up (10 s operation timeout) is not started. Without this, scans
// arriving faster than they finish piled up until the JavaScript heap ran out (local test: 2 nodes, 10^5 records,
// WO at 50 ops/s: heap limit reached within a minute).
const SCAN_CONCURRENCY = Number(process.env.SCAN_CONCURRENCY || 2)
let scans = 0; const waiting = []
const gate = async (req, fn) => {
  if (scans >= SCAN_CONCURRENCY) await new Promise(r => waiting.push(r))
  scans++
  try { return (req && req.socket.destroyed) ? null : await fn() } finally { scans--; const n = waiting.shift(); if (n) n() }
}
app.post('/query', handle(async (req, res) => {
  // no query language: a key-range scan when the criteria fix a key prefix, otherwise a full scan,
  // followed by client-side filtering (as an application would)
  const c = { ...(req.body || {}) }
  const range = c._prefix ? { gte: c._prefix, lt: c._prefix + '\xff' } : {}
  delete c._prefix
  const crit = Object.entries(c)
  const rows = await gate(req, () => scan(range, false, d => crit.every(([k, v]) => d[k] === v)))
  if (rows === null) return   // the client left before the scan started
  res.json({ results: rows })
}))
app.get('/snapshot', handle(async (req, res) => res.json(await gate(null, () => scan({}, true)))))
app.get('/admin/mem', (req, res) => res.json(process.memoryUsage()))   // diagnostics (heap vs. resident memory)
app.get('/admin/key', (req, res) => res.json({ base: base.key.toString('hex'), writer: base.local.key.toString('hex') }))
// indexer: false adds a writer that does not take part in ordering checkpoints (fewer indexers, less coordination)
app.post('/admin/add-writer', handle(async (req, res) => { await base.append({ addWriter: req.body.key, indexer: req.body.indexer !== false }); res.json({ ok: 1 }) }))
app.listen(PORT, () => console.log('autobase wrapper on', PORT, 'base key', base.key.toString('hex')))
