// HTTP wrapper exposing a Gun.js peer through the HttpKV contract of bench/adapters.py:
//   GET /kv/:key  PUT /kv/:key  POST /bulk  POST /query {criteria}  GET /snapshot
// npm i gun express   (record the version in the Baselines sheet)
// Each node runs one wrapper; PEERS lists the other nodes' Gun relay URLs (full mesh), e.g.
//   PEERS=http://10.0.1.12:8765/gun,http://10.0.2.21:8765/gun node gun_http.mjs
import express from 'express'
import http from 'http'
import Gun from 'gun'

const PORT = Number(process.env.PORT || 7004)        // HttpKV API
const GUN_PORT = Number(process.env.GUN_PORT || 8765) // Gun relay (peer-to-peer traffic)
const PEERS = (process.env.PEERS || '').split(',').filter(Boolean)

const relay = http.createServer(Gun.serve).listen(GUN_PORT)
const gun = Gun({ web: relay, peers: PEERS, file: process.env.GUN_DIR || 'radata', radisk: true, axe: false, multicast: false })
const root = gun.get('bench')

// Schema. Each document is stored as one JSON string, as a property of the set node 'bench' (key = _id), so
// merging stays per document (HAM resolves concurrent puts per property by state, i.e. last writer wins).
// The earlier schema made every document a child node ({json: ...}); listing the set then had to subscribe to
// 10,000 child nodes (root.map().once()), and those subscriptions were never fully released: the heap grew by
// about 2 MB per 1,000 documents on every scan until the node ran out of memory (WO issues 5 scans/s). With the
// documents as properties of one node, a scan is one read of that node. GUN_SCHEMA=nodes restores the old schema.
const FLAT = (process.env.GUN_SCHEMA || 'flat') !== 'nodes'
// Gun calls a put's callback when the write is acknowledged. In an 8-peer mesh that acknowledgement sometimes
// never comes, and a bulk load or a test run then waited forever. PUT_ACK_TIMEOUT_MS bounds the wait: an
// unacknowledged put fails (an error in the results) instead of hanging; the local write itself is kept by Gun.
const PUT_ACK_TIMEOUT_MS = Number(process.env.PUT_ACK_TIMEOUT_MS || 8000)
const GET_TIMEOUT_MS = Number(process.env.GET_TIMEOUT_MS || 8000)
const encode = doc => FLAT ? JSON.stringify(doc) : { json: JSON.stringify(doc) }
const decode = v => FLAT ? (typeof v === 'string' ? JSON.parse(v) : null) : (v && typeof v.json === 'string' ? JSON.parse(v.json) : null)
const put = (key, doc) => new Promise((ok, fail) => {
  let done = false
  const t = setTimeout(() => { if (!done) { done = true; fail(new Error('put not acknowledged within ' + PUT_ACK_TIMEOUT_MS + ' ms')) } }, PUT_ACK_TIMEOUT_MS)
  root.get(key).put(encode(doc), ack => {
    if (done) return
    done = true; clearTimeout(t)
    ack.err ? fail(new Error(ack.err)) : ok()
  })
})
const get = key => new Promise(ok => {
  const node = FLAT ? localSet() : undefined
  if (node && typeof node[key] === 'string') { try { return ok(JSON.parse(node[key])) } catch (e) { /* fall through */ } }
  let done = false
  const t = setTimeout(() => { if (!done) { done = true; ok(null) } }, GET_TIMEOUT_MS)
  root.get(key).once(v => { if (done) return; done = true; clearTimeout(t); ok(decode(v)) })
})

// Listing the set.
// flat: one read of the set node; its properties are the documents.
// nodes (old schema): Gun has no end-of-scan signal, so a scan ends when no new document has arrived for
// SCAN_QUIET_MS (or after SCAN_MAX_MS), and its listener is then removed (the quiet period is part of every scan's
// latency and must be stated with Gun's query results).
const SCAN_QUIET_MS = Number(process.env.SCAN_QUIET_MS || 300)
const SCAN_MAX_MS = Number(process.env.SCAN_MAX_MS || 60000)
// flat schema, local replica: the set node in this peer's own graph (gun._.graph), filled by its own writes and by
// the puts its peers send. root.once() on the set also asks every peer for the whole node; at 10^5 documents that
// is a ~200 MB message from each of 7 peers on every query, which ran the peers out of memory in the pilot.
// Reads and scans therefore use the local replica, as for the other systems (Autobase reads its local view;
// OptimusDB, Corrosion and Iroh read their own store). GUN_READ=network restores root.once() for everything.
const LOCAL = (process.env.GUN_READ || 'local') !== 'network'
const localSet = () => (LOCAL && gun._ && gun._.graph) ? gun._.graph['bench'] : undefined
const allFlat = () => new Promise(ok => {
  const node = localSet()
  if (node) return ok(node)
  let done = false
  const t = setTimeout(() => { if (!done) { done = true; ok({}) } }, SCAN_MAX_MS)
  root.once(n => { if (done) return; done = true; clearTimeout(t); ok(n || {}) })
})
// Client-side filtering. Each document is stored as its JSON text, so a criterion field:value appears in the text
// exactly as JSON.stringify writes it ("region":"eu-west"); a document without that text cannot match and is not
// parsed. Candidates are parsed and checked field by field, so the result is exactly the filter's. Parsing all
// 10^5 documents for every query allocated ~0.5 GB per scan and, with several scans in flight, ran out of memory.
const needles = c => Object.entries(c).filter(([, v]) => v === null || ['string', 'number', 'boolean'].includes(typeof v))
  .map(([k, v]) => JSON.stringify(k) + ':' + JSON.stringify(v))
const filterFlat = (node, c) => {
  const ns = needles(c); const out = []
  for (const k in node) {
    if (k === '_') continue
    const v = node[k]
    if (typeof v !== 'string' || !ns.every(n => v.includes(n))) continue
    let d; try { d = JSON.parse(v) } catch (e) { continue }
    if (Object.entries(c).every(([f, x]) => d[f] === x)) out.push(d)
  }
  return out
}
const docsFlat = node => filterFlat(node, {})
// At most SCAN_CONCURRENCY scans at a time (the rest wait their turn; the wait is part of their latency), so
// memory stays bounded when scans arrive faster than they finish.
const SCAN_CONCURRENCY = Number(process.env.SCAN_CONCURRENCY || 2)
let scans = 0; const waiting = []
const gate = async (fn, req) => {
  if (scans >= SCAN_CONCURRENCY) await new Promise(r => waiting.push(r))
  scans++
  try { return (req && req.socket.destroyed) ? null : await fn() } finally { scans--; const n = waiting.shift(); if (n) n() }
}
const allNodes = () => new Promise(ok => {
  const out = new Map(); const t0 = Date.now(); let last = t0
  const chain = root.map().once((v, k) => { last = Date.now(); if (v && typeof v.json === 'string') out.set(k, v.json) })
  const tick = setInterval(() => {
    const now = Date.now()
    if (now - last >= SCAN_QUIET_MS || now - t0 >= SCAN_MAX_MS) {
      clearInterval(tick)
      try { chain.off() } catch (e) { /* listener already gone */ }
      ok([...out.values()].map(j => JSON.parse(j)))
    }
  }, 50)
})
const all = FLAT ? async () => docsFlat(await allFlat()) : allNodes

const app = express(); app.use(express.json({ limit: '64mb' }))
app.get('/kv/:key', async (req, res) => { const d = await get(req.params.key); d ? res.json(d) : res.status(404).end() })
app.put('/kv/:key', async (req, res) => { try { await put(req.params.key, req.body); res.json({ ok: 1 }) } catch (e) { res.status(500).send(e.message) } })
// Bulk load: up to BULK_CONCURRENCY puts in flight, each still waiting for its own acknowledgement.
// (One put at a time made a 10^5-record preload take well over an hour.)
const BULK_CONCURRENCY = Number(process.env.BULK_CONCURRENCY || 64)
app.post('/bulk', async (req, res) => {
  try {
    // A put that is not acknowledged is retried once; documents still unacknowledged are reported, not hidden.
    const docs = req.body; let next = 0; const unacked = []
    const worker = async () => {
      while (next < docs.length) {
        const d = docs[next++]
        try { await put(d._id, d) } catch (e) { try { await put(d._id, d) } catch (e2) { unacked.push(d._id) } }
      }
    }
    await Promise.all(Array.from({ length: Math.min(BULK_CONCURRENCY, docs.length) }, worker))
    if (unacked.length) console.log('bulk: ' + unacked.length + ' puts not acknowledged after a retry')
    res.json({ ok: docs.length - unacked.length, unacked: unacked.length })
  } catch (e) { res.status(500).send(e.message) }
})
app.post('/query', async (req, res) => {
  const c = req.body || {}
  try {
    const rows = await gate(async () => FLAT ? filterFlat(await allFlat(), c)
      : (await allNodes()).filter(d => Object.entries(c).every(([k, v]) => d[k] === v)), req)   // client-side filtering
    if (rows === null) return   // the client left before the scan started (a scan that is not started is not run)
    res.json({ results: rows })
  } catch (e) { res.status(500).send(String(e && e.message || e)) }
})
app.get('/snapshot', async (req, res) => res.json(await gate(all)))
// diagnostics: documents in this peer's local replica (flat schema)
app.get('/admin/local', (req, res) => { const n = localSet(); res.json({ local: n ? Object.keys(n).length - 1 : 0 }) })
app.listen(PORT, () => console.log('gun wrapper on', PORT, 'relay on', GUN_PORT, 'peers', PEERS))
