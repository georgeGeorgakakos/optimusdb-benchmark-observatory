"""System adapters for the decentralized data stores under test (OptimusDB, Corrosion and OpenDHT natively; Gun.js, Autobase + Hyperbee and Iroh docs via the HTTP wrappers in wrappers/). Every system under test exposes the same five async operations
so that the load generator, workloads and metrics are identical across systems.

    execute(kind, key, payload) -> rows | None
        kind in {"read", "update", "insert", "query"}
    load(docs)                  bulk-load the initial dataset (not timed)
    sql(statement)              E3 only; returns number of rows
    snapshot_hash()             E8 only; hash of the replica's full state
"""
import base64, asyncio, hashlib, json, os, time
from urllib.parse import quote, urlencode

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None


class Adapter:
    name = "base"

    async def open(self): ...
    async def close(self): ...
    async def load(self, docs): raise NotImplementedError
    async def execute(self, kind, key, payload): raise NotImplementedError
    async def sql(self, statement): raise NotImplementedError(f"{self.name}: SQL not supported")
    async def load_allocations(self, allocs):
        """E3 allocation records; stored as documents unless the system has an `allocations` table."""
        await self.load(allocs)
    async def snapshot_hash(self): raise NotImplementedError
    # True when query() evaluates range operators ({"field": {"$gte": x}}) inside the system (E3 Q3 uses them then;
    # otherwise the harness filters ranges in the client).
    native_ops = False
    async def get_doc(self, key):
        """The current document stored under `key` on this replica, or None (E5 loss check)."""
        lst = await self.query({"_id": key})
        return lst[0] if lst else None


# Reading a whole replica to compare replicas (E5) can take far longer than one operation, especially on an
# edge host right after a partition; it must not fail on the 10 s per-operation timeout.
SNAPSHOT_TIMEOUT = 120.0


def _hash_docs(docs):
    h = hashlib.sha256()
    for d in sorted(docs, key=lambda x: x.get("_id", "")):
        d = {k: v for k, v in d.items() if not k.startswith("_source")}
        h.update(json.dumps(d, sort_keys=True).encode())
    return h.hexdigest()


def _batch_size(docs, cap=200, max_bytes=4 * 1024 * 1024):
    """Documents per bulk request so that one request stays below ~4 MB (64 KB documents -> 64 per batch)."""
    if not docs: return cap
    one = len(json.dumps(docs[0])) + 64
    return max(1, min(cap, max_bytes // one))


# --------------------------------------------------------------------------- OptimusDB
class OptimusDB(Adapter):
    """HTTP command API of an OptimusDB agent (POST /<context>/command).

    Request format taken from the repository's curlCommands examples:
      {"method": {"cmd": "crudput", "argcnt": 2}, "args": [...], "dstype": "dsswres",
       "criteria": [ {...document...} ]}
    Query strategy and consistency travel in "options" (app/service.go QueryOptions).
    """
    name = "optimusdb"
    native_ops = True          # the document query evaluates $gte/$lte/$gt/$lt/$in/... (matchesCondition)

    def __init__(self, base_url, context="swarmkb", dstype="dsswres", strategy="LOCAL_THEN_REMOTE_MERGE",
                 consistency="BEST_EFFORT", time_budget_ms=1200, quorum_n=0, credential=None, timeout=10.0,
                 sql_tables=False, annotate=False):
        self.url = f"{base_url.rstrip('/')}/{context}/command"
        self.base = base_url.rstrip('/'); self.context = context
        self.dstype, self.strategy, self.consistency = dstype, strategy, consistency
        self.time_budget_ms, self.quorum_n, self.timeout = time_budget_ms, quorum_n, timeout
        self.credential = credential   # E10: callable(method, body) -> headers with a Verifiable Presentation
        self.sql_tables = sql_tables   # E3 SQLite path: load() writes tables `resources` and `allocations` via sqldml
        # annotate_source adds _source/_trace (which peer answered, trace id) to every returned row: a diagnostic
        # no baseline returns, so the benchmark turns it off (annotate=True restores OptimusDB's default).
        self.annotate = annotate
        self.client = None
        # Reads use GET /<context>/doc/<id> when the build has it (same answer as the query command with
        # criteria [{"_id": id}]); None = not tried yet, False = this build has no such endpoint.
        self._doc_get = None

    async def open(self):
        self.client = httpx.AsyncClient(timeout=self.timeout, limits=httpx.Limits(max_connections=512))

    async def close(self):
        if self.client: await self.client.aclose()

    def _body(self, cmd, argcnt=1, criteria=None, sqldml="", options=None):
        b = {"method": {"cmd": cmd, "argcnt": argcnt}, "args": ["", ""], "dstype": self.dstype,
             "sqldml": sqldml, "graph_traversal": [{}], "criteria": criteria or [{}]}
        if options: b["options"] = options
        return b

    async def _post(self, body, timeout=None):
        headers = self.credential("POST", body) if self.credential else {}
        r = await self.client.post(self.url, json=body, headers=headers, **({"timeout": timeout} if timeout else {}))
        if r.status_code == 401:
            raise PermissionError("401 " + r.text[:80])
        r.raise_for_status()
        txt = r.text
        if txt.startswith("ERROR"):
            raise RuntimeError(txt[:120])
        try:
            return r.json()
        except ValueError:
            return txt

    def _opts(self):
        o = {"strategy": self.strategy, "consistency": self.consistency, "time_budget_ms": self.time_budget_ms,
             "include_local": True, "annotate_source": self.annotate, "dstype": self.dstype}
        if self.strategy.startswith("QUORUM_"):          # QUORUM_2 -> strategy QUORUM, quorum_n 2
            o["strategy"] = "QUORUM"; o["quorum_n"] = int(self.strategy.split("_")[1])
        return o

    async def load(self, docs, batch=None):
        if self.sql_tables:
            return await self._sql_load_resources(docs)
        batch = batch or _batch_size(docs)
        for i in range(0, len(docs), batch):
            await self._post(self._body("crudput", 2, docs[i:i + batch]), timeout=600)

    # --- E3 SQLite path: OptimusDB's relational store is reached with the `sqldml` command. Its schema has no
    # `resources` / `allocations` tables, so they are created here and filled with multi-row INSERTs.
    RES_COLS = ("id", "resource_provider", "resource_type", "status", "region", "cpu_capacity", "memory_capacity",
                "storage", "version", "doc")

    @staticmethod
    def _lit(v):
        if v is None: return "NULL"
        if isinstance(v, (int, float)): return str(v)
        return "'" + str(v).replace("'", "''") + "'"

    async def _sql_exec(self, stmt):
        res = await self._post(self._body("sqldml", 1, sqldml=stmt), timeout=600)
        if isinstance(res, str) and "error" in res.lower():
            raise RuntimeError(res[:120])
        return res

    async def _sql_load_resources(self, docs, rows_per_stmt=200):
        await self._sql_exec("CREATE TABLE IF NOT EXISTS resources (id TEXT PRIMARY KEY, resource_provider TEXT, "
                             "resource_type TEXT, status TEXT, region TEXT, cpu_capacity INTEGER, memory_capacity INTEGER, "
                             "storage INTEGER, version INTEGER, doc TEXT)")
        # the same secondary indexes as Corrosion's schema and OptimusDB's default field indexes
        await self._sql_exec("CREATE INDEX IF NOT EXISTS resources_status ON resources (status)")
        await self._sql_exec("CREATE INDEX IF NOT EXISTS resources_region ON resources (region)")
        for i in range(0, len(docs), rows_per_stmt):
            vals = []
            for x in docs[i:i + rows_per_stmt]:
                row = [x.get("_id")] + [x.get(c) for c in self.RES_COLS[1:-1]] + [json.dumps(x)]
                vals.append("(" + ", ".join(self._lit(v) for v in row) + ")")
            await self._sql_exec(f"INSERT OR REPLACE INTO resources ({', '.join(self.RES_COLS)}) VALUES " + ", ".join(vals))

    async def load_allocations(self, allocs, rows_per_stmt=500):
        if not self.sql_tables:
            return await self.load(allocs)
        await self._sql_exec("CREATE TABLE IF NOT EXISTS allocations (id TEXT PRIMARY KEY, resource_id TEXT, app TEXT)")
        await self._sql_exec("CREATE INDEX IF NOT EXISTS allocations_resource_id ON allocations (resource_id)")
        for i in range(0, len(allocs), rows_per_stmt):
            vals = ", ".join("(" + ", ".join(self._lit(v) for v in (a["_id"], a["resource_id"], a["app"])) + ")"
                             for a in allocs[i:i + rows_per_stmt])
            await self._sql_exec(f"INSERT OR REPLACE INTO allocations (id, resource_id, app) VALUES {vals}")

    async def _read_get(self, key):
        """Read by id with GET /<context>/doc/<id>; None when the build has no such endpoint (404 on first use)."""
        # the query string is built once per adapter (strategy and store do not change between reads)
        if getattr(self, "_doc_qs", None) is None or self._doc_qs[0] != (self.dstype, self.strategy):
            self._doc_qs = ((self.dstype, self.strategy), urlencode({"dstype": self.dstype, "strategy": self.strategy}))
        r = await self.client.get(f"{self.base}/{self.context}/doc/{quote(str(key), safe='')}?{self._doc_qs[1]}")
        if r.status_code == 404 and self._doc_get is None and not r.content.startswith(b"{"):
            self._doc_get = False      # older build: Go's "404 page not found"
            return None
        self._doc_get = True
        if r.status_code == 401:
            raise PermissionError("401 " + r.text[:80])
        r.raise_for_status()
        return _count(r.json())

    async def execute(self, kind, key, payload):
        if kind == "read":
            if self._doc_get is not False and not self.credential and not self.strategy.startswith("QUORUM_"):
                n = await self._read_get(key)
                if n is not None: return n
            res = await self._post(self._body("query", 2, [{"_id": key}], options=self._opts()))
            return _count(res)
        if kind in ("update", "insert"):
            payload = dict(payload); payload["writer_ts"] = time.time()
            cmd = "crudput" if kind == "insert" else "crudupdate"
            if kind == "update":
                body = self._body(cmd, 2, [{"_id": key}]); body["UpdateData"] = [payload]
            else:
                body = self._body(cmd, 2, [payload])
            await self._post(body)
            return 1
        if kind == "query":
            res = await self._post(self._body("query", 2, [payload], options=self._opts()))
            return _count(res)
        raise ValueError(kind)

    async def query(self, criteria):
        """Document query through the CRDT store; returns the list of matching documents."""
        res = await self._post(self._body("query", 2, [criteria], options=self._opts()))
        return _docs(res)

    async def sql(self, statement):
        res = await self._post(self._body("sqldml", 1, sqldml=statement))
        return _count(res)

    async def snapshot_hash(self):
        saved = self.strategy; self.strategy = "LOCAL_ONLY"
        try:
            res = await self._post(self._body("query", 2, [{}], options=self._opts()), timeout=SNAPSHOT_TIMEOUT)
        finally:
            self.strategy = saved
        docs = res if isinstance(res, list) else (res.get("results") or res.get("data") or []) if isinstance(res, dict) else []
        return _hash_docs(docs), len(docs)

    async def status(self):
        r = await self.client.get(f"{self.base}/{self.context}/agent/status")
        return r.json()


def _docs(res):
    if isinstance(res, list): return res
    if isinstance(res, dict) and isinstance(res.get("data"), dict):
        return _docs(res["data"])
    if isinstance(res, dict):
        for k in ("results", "data", "rows", "items", "records"):
            if isinstance(res.get(k), list): return res[k]
    return []


def _count(res):
    if isinstance(res, list): return len(res)
    if isinstance(res, dict) and isinstance(res.get("data"), dict):   # OptimusDB: {"status": 200, "data": {"records": [...]}}
        return _count(res["data"])
    if isinstance(res, dict):
        for k in ("results", "data", "rows", "items", "records"):   # OptimusDB sqldml answers {"records": [...]}
            if isinstance(res.get(k), list): return len(res[k])
        if "count" in res: return int(res["count"])
    return -1


# --------------------------------------------------------------------------- generic HTTP wrapper
class HttpKV(Adapter):
    """For library systems without a server (Gun.js, Autobase + Hyperbee, Iroh docs):
    run the small wrapper in wrappers/ next to each node; it exposes
      GET /kv/<key>   PUT /kv/<key>   POST /query {criteria}   GET /snapshot   POST /sql {statement}
    """
    def __init__(self, base_url, name, timeout=10.0):
        self.base, self.name, self.timeout = base_url.rstrip('/'), name, timeout
        self.client = None

    async def open(self):
        self.client = httpx.AsyncClient(timeout=self.timeout, limits=httpx.Limits(max_connections=512))

    async def close(self):
        if self.client: await self.client.aclose()

    async def load(self, docs, batch=None):
        batch = batch or _batch_size(docs)
        for i in range(0, len(docs), batch):
            (await self.client.post(f"{self.base}/bulk", json=docs[i:i + batch], timeout=600)).raise_for_status()

    async def execute(self, kind, key, payload):
        if kind == "read":   # the document is decoded, as for every other system
            r = await self.client.get(f"{self.base}/kv/{key}"); r.raise_for_status(); r.json(); return 1
        if kind in ("update", "insert"):
            payload = dict(payload); payload["writer_ts"] = time.time()
            r = await self.client.put(f"{self.base}/kv/{key}", json=payload); r.raise_for_status(); return 1
        r = await self.client.post(f"{self.base}/query", json=payload); r.raise_for_status()
        return _count(r.json())

    async def query(self, criteria):
        r = await self.client.post(f"{self.base}/query", json=criteria); r.raise_for_status()
        js = r.json(); return js.get("results", []) if isinstance(js, dict) else js

    async def sql(self, statement):
        raise NotImplementedError(f"{self.name}: no SQL interface")

    async def get_doc(self, key):
        r = await self.client.get(f"{self.base}/kv/{key}")
        if r.status_code == 404: return None
        r.raise_for_status(); return r.json()

    async def snapshot_hash(self):
        r = await self.client.get(f"{self.base}/snapshot", timeout=SNAPSHOT_TIMEOUT); r.raise_for_status()
        docs = r.json(); return _hash_docs(docs), len(docs)


# --------------------------------------------------------------------------- Corrosion
class Corrosion(Adapter):
    """Corrosion agent HTTP API (superfly/corrosion): POST /v1/transactions with a JSON array of
    statements ([sql, params]); POST /v1/queries with one statement, answered as NDJSON events
    ({"columns":...}, {"row":[rowid,[...]]}, {"eoq":...}). Schema files define table `resources`
    (id TEXT PRIMARY KEY NOT NULL, region, status, cpu_capacity, memory_capacity, version, doc)."""
    name = "corrosion"

    def __init__(self, base_url, timeout=10.0):
        self.base, self.timeout, self.client = base_url.rstrip('/'), timeout, None

    async def open(self):
        self.client = httpx.AsyncClient(timeout=self.timeout, limits=httpx.Limits(max_connections=512))

    async def close(self):
        if self.client: await self.client.aclose()

    async def _tx(self, stmts, timeout=None):
        r = await self.client.post(f"{self.base}/v1/transactions", json=stmts, **({"timeout": timeout} if timeout else {})); r.raise_for_status()

    async def _q(self, sql, params=None, timeout=None):
        r = await self.client.post(f"{self.base}/v1/queries", json=[sql, params] if params else sql,
                                   **({"timeout": timeout} if timeout else {})); r.raise_for_status()
        # NDJSON events (columns, row..., eoq, or error) decoded in one call: the harness should add as little client
        # work as possible for every system. An error event is an error, not an empty result.
        lines = [l for l in r.text.splitlines() if l.strip()]
        events = json.loads("[" + ",".join(lines) + "]") if lines else []
        for e in events:
            if isinstance(e, dict) and "error" in e: raise RuntimeError(f"corrosion: {e['error']}")
        return [e["row"][1] for e in events if isinstance(e, dict) and "row" in e]

    @staticmethod
    def _docs(rows):
        """The documents of rows whose first column is the stored JSON document, decoded in one call."""
        return json.loads("[" + ",".join(r[0] for r in rows) + "]") if rows else []

    @staticmethod
    def _ins(d):
        return ["INSERT INTO resources (id, region, status, cpu_capacity, memory_capacity, version, doc) VALUES (?,?,?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET region=excluded.region, status=excluded.status, version=excluded.version, doc=excluded.doc",
                [d["_id"], d["region"], d["status"], d["cpu_capacity"], d["memory_capacity"], d.get("version", 0), json.dumps(d)]]

    async def load(self, docs, batch=None):
        batch = batch or _batch_size(docs)
        for i in range(0, len(docs), batch):
            await self._tx([self._ins(d) for d in docs[i:i + batch]], timeout=600)

    async def execute(self, kind, key, payload):
        # Every system returns, and the client decodes, the same thing: the whole documents (TESTS.md 1.4). The
        # WO query used to fetch only the ids here, while every other system returned the matching documents.
        if kind == "read":
            return len(self._docs(await self._q("SELECT doc FROM resources WHERE id = ?", [key])))
        if kind in ("update", "insert"):
            payload = dict(payload); payload["writer_ts"] = time.time(); payload["_id"] = key
            await self._tx([self._ins(payload)]); return 1
        rows = await self._q("SELECT doc FROM resources WHERE region = ? AND status = ?", [payload["region"], payload["status"]])
        return len(self._docs(rows))

    async def query(self, criteria):
        where = " AND ".join(f"{k} = ?" for k in criteria) or "1=1"
        rows = await self._q(f"SELECT doc FROM resources WHERE {where}", list(criteria.values()) or None)
        return [json.loads(r[0]) for r in rows]

    async def sql(self, statement): return len(await self._q(statement))

    async def get_doc(self, key):
        rows = await self._q("SELECT doc FROM resources WHERE id = ?", [key])
        return json.loads(rows[0][0]) if rows else None

    async def load_allocations(self, allocs, batch=200):
        # schema file adds: CREATE TABLE allocations (id TEXT PRIMARY KEY NOT NULL, resource_id TEXT, app TEXT)
        for i in range(0, len(allocs), batch):
            await self._tx([["INSERT OR REPLACE INTO allocations (id, resource_id, app) VALUES (?,?,?)", [x["_id"], x["resource_id"], x["app"]]] for x in allocs[i:i + batch]])

    async def snapshot_hash(self):
        rows = await self._q("SELECT doc FROM resources", timeout=SNAPSHOT_TIMEOUT)
        return _hash_docs([json.loads(r[0]) for r in rows]), len(rows)


# --------------------------------------------------------------------------- OpenDHT
class OpenDHT(Adapter):
    """OpenDHT REST proxy (dhtnode --proxyserver <port>): GET /key/<k> streams the values stored under
    InfoHash::get(k) as NDJSON ({"id":..,"data":<base64>,..}); POST /key/<k> with {"data":<base64>,"permanent":true}
    stores a value that the proxy keeps re-announcing. A key can hold several values: updates are written as new
    values carrying the document's application-level version, and reads return the value with the latest
    (writer_ts, version). A DHT cannot enumerate keys, so predicate scans are not supported (raised as
    NotImplementedError and reported as unsupported); snapshots read the keys this harness has written."""
    name = "opendht"
    KEYS = set()          # keys written by the harness (shared by all OpenDHT adapters in the process)

    def __init__(self, base_url, timeout=10.0, prefix="bench:"):
        self.base, self.timeout, self.prefix, self.client = base_url.rstrip('/'), timeout, prefix, None

    async def open(self):
        self.client = httpx.AsyncClient(timeout=self.timeout, limits=httpx.Limits(max_connections=512))

    async def close(self):
        if self.client: await self.client.aclose()

    async def _put(self, key, doc):
        body = {"data": base64.b64encode(json.dumps(doc).encode()).decode(), "permanent": True}
        r = await self.client.post(f"{self.base}/key/{self.prefix}{key}", json=body); r.raise_for_status()
        OpenDHT.KEYS.add(key)

    @staticmethod
    def latest(text):
        best = None
        for line in text.splitlines():
            line = line.strip()
            if not line: continue
            try: d = json.loads(base64.b64decode(json.loads(line)["data"]))
            except (ValueError, KeyError): continue
            k = (d.get("writer_ts", 0), d.get("version", 0))   # last writer wins by issue time, as in the other systems
            if best is None or k > best[0]: best = (k, d)
        return best[1] if best else None

    async def get(self, key):
        r = await self.client.get(f"{self.base}/key/{self.prefix}{key}"); r.raise_for_status()
        return self.latest(r.text)

    async def load(self, docs):
        sem = asyncio.Semaphore(64)
        async def one(d):
            async with sem: await self._put(d["_id"], d)
        await asyncio.gather(*(one(d) for d in docs))

    async def execute(self, kind, key, payload):
        if kind == "read": return 1 if await self.get(key) else 0
        if kind in ("update", "insert"):
            payload = dict(payload); payload["writer_ts"] = time.time(); payload["_id"] = key
            await self._put(key, payload); return 1
        raise NotImplementedError("opendht: predicate scans are not supported by a DHT")

    async def get_doc(self, key):
        return await self.get(key)

    async def query(self, criteria):
        if criteria and set(criteria) <= {"_id", "id"}:     # an empty filter ({}) is a full scan, not a key lookup
            d = await self.get(criteria.get("_id", criteria.get("id"))); return [d] if d else []
        raise NotImplementedError("opendht: predicate queries are not supported by a DHT")

    async def snapshot_hash(self):
        docs = [d for d in await asyncio.gather(*(self.get(k) for k in sorted(OpenDHT.KEYS))) if d]
        return _hash_docs(docs), len(docs)


# --------------------------------------------------------------------------- in-memory (tests only)
class InMemory(Adapter):
    """Used only by tests/ and `--dry-run` to exercise the pipeline; never a baseline."""
    name = "inmemory"

    def __init__(self, delay_ms=1.0):
        self.d, self.delay = {}, delay_ms / 1000.0

    async def load(self, docs):
        for x in docs: self.d[x["_id"]] = x

    async def execute(self, kind, key, payload):
        await asyncio.sleep(self.delay)
        if kind == "read": return 1 if key in self.d else 0
        if kind in ("update", "insert"): self.d[key] = payload; return 1
        return sum(1 for v in self.d.values() if v.get("region") == payload["region"] and v.get("status") == payload["status"])

    async def snapshot_hash(self):
        return _hash_docs(list(self.d.values())), len(self.d)

    async def query(self, criteria):
        return [d for d in self.d.values() if all(d.get(k) == v for k, v in criteria.items())]



def make(cfg):
    """Build an adapter from a config dict: {type: optimusdb|http|corrosion|opendht|inmemory, ...}."""
    t = cfg["type"]; kw = {k: v for k, v in cfg.items() if k not in ("type", "label")}
    ad = {"optimusdb": OptimusDB, "http": HttpKV, "corrosion": Corrosion, "opendht": OpenDHT, "inmemory": InMemory}[t](**kw)
    ad.spec = dict(cfg)       # lets a load-generator worker process build an identical adapter
    return ad
