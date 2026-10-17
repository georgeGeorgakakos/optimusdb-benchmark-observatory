"""Pipeline tests with the in-memory adapter (no cluster needed). These validate the
harness itself — they produce no experimental results."""
import asyncio, csv, os, statistics, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import numpy as np
from bench import spec, workloads, loadgen, metrics, adapters


def test_mix_proportions():
    w = workloads.Workload("WO", 10_000, "256B", seed=3)
    kinds = [w.next_op()[0] for _ in range(20_000)]
    share = {k: kinds.count(k) / len(kinds) for k in set(kinds)}
    assert abs(share["read"] - 0.60) < 0.02 and abs(share["update"] - 0.20) < 0.02
    assert abs(share["insert"] - 0.10) < 0.02 and abs(share["query"] - 0.10) < 0.02


def test_zipf_skew_and_range():
    z = workloads.Zipfian(1000, 0.99)
    xs = [z.next() for _ in range(50_000)]
    assert min(xs) >= 0 and max(xs) < 1000
    assert xs.count(0) / len(xs) > 0.05      # head is hot


def test_doc_size():
    import json
    for s, n in workloads.SIZE_BYTES.items():
        assert abs(len(json.dumps(workloads.make_doc(7, s))) - n) <= 16


def test_open_loop_rate_and_no_coordinated_omission():
    class Slow(adapters.InMemory):
        async def execute(self, kind, key, payload):
            await asyncio.sleep(0.05); return 1
    recs, dropped = asyncio.run(loadgen.run_open_loop(Slow(), workloads.Workload("WC", 100), rate=100, duration_s=3, poisson=False))
    assert 280 <= len(recs) <= 310 and dropped == 0          # schedule kept despite 50 ms service time
    assert min(r.latency_ms for r in recs) >= 49              # latency measured from scheduled start


def test_stats():
    a = np.random.default_rng(1).normal(100, 5, 10); b = a + 20
    r = metrics.compare(a, b)
    assert r["p_raw"] < 0.001 and r["magnitude"] == "large" and r["cliffs_delta"] == -1.0
    adj, sig = metrics.holm([0.01, 0.04, 0.03])
    assert [round(x, 2) for x in adj] == [0.03, 0.06, 0.06] and sig == [True, False, False]
    m, h = metrics.ci95([1, 2, 3, 4, 5]); assert m == 3 and abs(h - 1.963) < 0.01


def test_e1_dry_run_columns(tmp_path, monkeypatch):
    monkeypatch.setenv("BENCH_RESULTS", str(tmp_path))
    import importlib; from bench import runner; importlib.reload(runner)
    cfg = dict(seed=1, run=dict(rate=50, duration_s=2, warmup_s=0.5, poisson=True), data=dict(records=500),
               systems={"mem": {"type": "inmemory", "delay_ms": 2}})
    class Args: systems = ["mem"]; reps = 1; yes = True
    asyncio.run(runner.e1(cfg, Args))
    rows = list(csv.DictReader(open(tmp_path / "E1_raw.csv")))
    e1 = next(e for e in spec.EXPERIMENTS if e["id"] == "E1")
    assert list(rows[0].keys()) == e1["raw"] and len(rows) == 7   # 4 workloads at 2 KB + WO at 3 other sizes
    assert all(float(r["p99_ms"]) >= 2 for r in rows)


def test_workbook_columns_match_spec():
    import openpyxl
    p = os.path.join(os.path.dirname(__file__), "..", "..", "OptimusDB_Section8_Evidence.xlsx")
    if not os.path.exists(p): return
    wb = openpyxl.load_workbook(p, read_only=True)
    for e in spec.EXPERIMENTS:
        hdr = [c.value for c in next(wb[e["id"] + "_raw"].iter_rows(min_row=3, max_row=3))]
        assert hdr[:len(e["raw"])] == e["raw"], e["id"]


def _mock(adapter, handler):
    import httpx
    adapter.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return adapter


def test_corrosion_adapter_parses_ndjson():
    import httpx, json as js
    def h(req):
        if req.url.path == "/v1/queries":
            body = '{"columns":["doc"]}\n{"row":[1,["{\\"_id\\":\\"a\\",\\"v\\":1}"]]}\n{"row":[2,["{\\"_id\\":\\"b\\",\\"v\\":2}"]]}\n{"eoq":{"time":0.1}}\n'
            return httpx.Response(200, text=body)
        assert js.loads(req.content)[0][0].startswith("INSERT INTO resources")
        return httpx.Response(200, json={"results": [{"rows_affected": 1}]})
    a = _mock(adapters.Corrosion("http://x"), h)
    assert asyncio.run(a.execute("read", "a", None)) == 2
    assert asyncio.run(a.execute("update", "a", workloads.make_doc(1, "256B"))) == 1
    h_, n = asyncio.run(a.snapshot_hash()); assert n == 2


def test_opendht_adapter_latest_value_and_unsupported_scan():
    import httpx, json as js, base64
    vals = [{"_id": "a", "version": 1, "writer_ts": 1.0, "status": "old"}, {"_id": "a", "version": 2, "writer_ts": 2.0, "status": "new"}]
    posted = []
    def h(req):
        if req.method == "POST":
            posted.append(js.loads(req.content)); return httpx.Response(200, json={"id": 1})
        assert req.url.path == "/key/bench:a"
        return httpx.Response(200, text="".join(js.dumps({"id": i, "data": base64.b64encode(js.dumps(v).encode()).decode()}) + "\n" for i, v in enumerate(vals)))
    a = _mock(adapters.OpenDHT("http://x"), h)
    assert asyncio.run(a.get("a"))["status"] == "new"
    assert asyncio.run(a.execute("update", "a", {"version": 3})) == 1 and posted[0]["permanent"] is True
    import pytest
    with pytest.raises(NotImplementedError): asyncio.run(a.execute("query", None, {"status": "Running"}))


def test_client_eval_queries():
    from bench import runner
    docs = [{"_id": "r1", "region": "eu-west", "status": "Running", "cpu_capacity": 8, "memory_capacity": 16384},
            {"_id": "r2", "region": "eu-west", "status": "Stopped", "cpu_capacity": 2, "memory_capacity": 4096},
            {"_id": "r3", "region": "us-east", "status": "Running", "cpu_capacity": 4, "memory_capacity": 8192},
            {"_id": "a1", "type": "allocation", "resource_id": "r1", "app": "x"}]
    class Q(adapters.InMemory):
        async def query(self, c): return [d for d in docs if all(d.get(k) == v for k, v in c.items())]
    q = Q(0)
    assert asyncio.run(runner.client_eval(q, "Q2", "r1")) == 2
    assert asyncio.run(runner.client_eval(q, "Q3", "r1")) == 1
    assert asyncio.run(runner.client_eval(q, "Q4", "r1")) == 2
    assert asyncio.run(runner.client_eval(q, "Q5", "r1")) == 1


def test_trace_uses_one_endpoint_per_node(monkeypatch, tmp_path):
    from bench import trace, runner
    seen = []
    class Fake(adapters.InMemory):
        def __init__(self, base_url=None, **kw): super().__init__(0.1); seen.append(base_url)
        async def query(self, c): return []
        async def snapshot_hash(self): return ('same', 0)
    monkeypatch.setattr(runner, "system_adapter", lambda cfg, sysid, **over: Fake(**over))
    p = tmp_path / "t.jsonl"; p.write_text('{"t": 0.0, "agent": 1, "op": "update", "key": "k", "doc": {"version": 1}}\n')
    cfg = {"agents": ["a1", "a2"], "replicas": {"corrosion": ["c1", "c2", "c3"]}, "systems": {}}
    asyncio.run(trace.replay(cfg, str(p), "corrosion", 50.0, 1))
    assert seen == ["c1", "c2", "c3"]


def test_cluster_reset_routing_and_nodes(monkeypatch):
    from bench import runner, cluster
    calls = []
    async def fake_reset(cfg, sysid, tier=None): calls.append((sysid, tier))
    monkeypatch.setattr(cluster, "reset", fake_reset)
    cfg = {"cluster": {"token": "t", "hosts": [{"name": "bench", "role": "bench", "ip": "10.88.0.2"},
                                                {"name": "cloud-a", "role": "cloud", "ip": "10.88.0.11"},
                                                {"name": "edge-a", "role": "edge", "ip": "10.88.0.15"}]}}
    asyncio.run(runner.cfg_reset(cfg, "corrosion")); asyncio.run(runner.cfg_reset(cfg, "iroh_edge"))
    assert calls == [("corrosion", None), ("iroh", "edge")]
    ns = runner.nodes_from(cfg)
    assert [n.name for n in ns] == ["cloud-a", "edge-a"] and ns[0].iface == "wg0" and ns[0].agent_url == "http://10.88.0.11:9100"
    assert [h["name"] for h in cluster.hosts_of(cfg, "edge")] == ["edge-a"]


def test_unsupported_ops_are_not_errors():
    from bench.loadgen import OpRecord
    from bench.metrics import run_summary
    recs = [OpRecord(0, 0, 0.01, "read", True), OpRecord(0, 0, 0.0, "query", False, "NotImplementedError: dht"),
            OpRecord(0, 0, 0.02, "update", False, "TimeoutError: ")]
    s = run_summary(recs, 1.0)
    assert s["unsupported"] == 1 and s["errors"] == 1 and s["ops"] == 2
    assert abs(s["supported_share"] - 2 / 3) < 1e-3


def test_lost_write_rule_allows_concurrent_overwrite():
    from bench.observe import AckLog
    a = AckLog()
    # two writers, overlapping in time: either final value is legitimate
    a.ack("k", 105, writer=0, issue_ts=10.0, ack_ts=10.2)
    a.ack("k", 103, writer=1, issue_ts=10.1, ack_ts=10.3)
    assert not a.is_lost("k", {"writer": 1, "version": 103, "writer_ts": 10.1})
    assert not a.is_lost("k", {"writer": 0, "version": 105, "writer_ts": 10.0})
    # a write issued after the final value's write completed must have won
    a.ack("k", 104, writer=1, issue_ts=12.0, ack_ts=12.1)
    assert a.is_lost("k", {"writer": 0, "version": 105, "writer_ts": 10.0})
    assert a.is_lost("k", None)


def test_lost_write_rule_partition_sides_are_concurrent():
    from bench.observe import AckLog
    a = AckLog(side_of=lambda w: 0 if w < 4 else 1)
    a.ack("k", 1, writer=0, issue_ts=10.0, ack_ts=10.1)     # side 0
    a.ack("k", 2, writer=5, issue_ts=20.0, ack_ts=20.1)     # side 1, later in wall time but concurrent
    assert not a.is_lost("k", {"writer": 0, "version": 1, "writer_ts": 10.0})
    a.ack("k", 3, writer=1, issue_ts=30.0, ack_ts=30.1)     # side 0, after the survivor completed
    assert a.is_lost("k", {"writer": 0, "version": 1, "writer_ts": 10.0})


def test_optimusdb_runtime_env_per_tier():
    from bench import cluster
    cfg = {"cluster": {"hosts": [{"name": "bench", "role": "bench", "ip": "x"},
                                 {"name": "cloud-a", "role": "cloud", "ip": "a", "cpus": 1.25, "mem": "3g"},
                                 {"name": "edge-a", "role": "edge", "ip": "b", "cpus": 0.75, "mem": "2g"},
                                 {"name": "far", "role": "edge", "ip": "c"}]}}
    hs = cluster.hosts_of(cfg)
    c, e, nolimit = (cluster.optimusdb_env(cfg, h) for h in hs)
    assert c["GOMAXPROCS"] == "2" and c["GOMEMLIMIT"] == "2457MiB" and c["GOGC"] == "200"
    assert e["GOMAXPROCS"] == "1" and e["GOMEMLIMIT"] == "1638MiB"
    assert c["OPTIMUSDB_LOG_LEVEL"] == "WARN" and c["OPTIMUSDB_ARGS"] == "-metrics=false"
    assert "GOMAXPROCS" not in nolimit and "GOMEMLIMIT" not in nolimit      # multi-host: no container limits known
    cfg["optimusdb_runtime"] = {"log_level": None, "go_limits": False, "env": {"SERVICE_CONCURRENCY": 1}}
    c = cluster.optimusdb_env(cfg, hs[0])
    assert "OPTIMUSDB_LOG_LEVEL" not in c and "GOMAXPROCS" not in c and c["SERVICE_CONCURRENCY"] == "1"
    s = cluster.runtime_summary(cfg)
    assert set(s["optimusdb"]) == {"cloud", "edge"} and s["corrosion"]["RUST_LOG"] == "warn"


def test_sql_records_are_counted():
    assert adapters._count({"records": [{"a": 1}, {"a": 2}]}) == 2
    assert adapters._count({"records": []}) == 0


def test_loss_check_is_bounded_when_reads_hang():
    from bench import observe
    import time as _t
    ack = observe.AckLog()
    for i in range(200):
        ack.ack(f"k{i}", 1, writer=0, issue_ts=1.0, ack_ts=1.1)

    async def read(_, k):
        if k.endswith("7"): await asyncio.sleep(60)          # hangs
        return {"writer": 0, "version": 1, "writer_ts": 1.0}

    t0 = _t.time()
    lost, checked, unreadable = asyncio.run(ack.lost(None, read, concurrency=50, read_timeout_s=0.3, budget_s=5))
    assert _t.time() - t0 < 5 and lost == 0 and unreadable == 20 and checked == 180


def test_loss_check_is_bounded_when_reads_hang():
    from bench import observe
    import time as _t
    ack = observe.AckLog()
    for i in range(200):
        ack.ack(f"k{i}", 1, writer=0, issue_ts=1.0, ack_ts=1.1)

    async def read(_, k):
        if k.endswith("7"): await asyncio.sleep(60)          # hangs
        return {"writer": 0, "version": 1, "writer_ts": 1.0}

    t0 = _t.time()
    lost, checked, unreadable = asyncio.run(ack.lost(None, read, concurrency=50, read_timeout_s=0.3, budget_s=5))
    assert _t.time() - t0 < 5 and lost == 0 and unreadable == 20 and checked == 180


def test_convergence_wait_respects_limit_with_slow_replica():
    from bench import observe
    import time as _t

    class Slow:
        async def snapshot_hash(self):
            await asyncio.sleep(60); return "h", 1

    t0 = _t.time()
    conv, same, _ = asyncio.run(observe.wait_convergence([Slow(), Slow()], _t.time(), timeout_s=2))
    assert not same and _t.time() - t0 < 5


def test_optimusdb_wrapped_sql_records_are_counted():
    assert adapters._count({"status": 200, "data": {"records": [{"a": 1}] * 3}}) == 3
    assert adapters._count({"status": 200, "data": [{"a": 1}, {"a": 2}]}) == 2
    assert adapters._docs({"status": 200, "data": {"records": [{"a": 1}]}}) == [{"a": 1}]


def test_opendht_full_scan_is_unsupported():
    import pytest
    ad = adapters.OpenDHT("http://127.0.0.1:1")
    with pytest.raises(NotImplementedError):
        asyncio.run(ad.query({}))


def test_wo_query_returns_documents_on_every_sql_baseline():
    """The WO query must fetch the matching documents (not only their ids) on Corrosion, as on every system."""
    import httpx, json as js
    seen = []
    def h(req):
        seen.append(js.loads(req.content)[0])
        body = '{"columns":["doc"]}\n{"row":[1,["{\\"_id\\":\\"a\\",\\"region\\":\\"eu\\"}"]]}\n{"eoq":{"time":0.1}}\n'
        return httpx.Response(200, text=body)
    a = _mock(adapters.Corrosion("http://x"), h)
    assert asyncio.run(a.execute("query", None, {"region": "eu", "status": "Running"})) == 1
    assert seen[-1].startswith("SELECT doc FROM resources WHERE region")


def test_limit_verdict_separates_client_and_node():
    from bench.runner import limit_verdict
    assert limit_verdict(30.0, 1.0, 140.0, 150.0) == "node"        # node CPU at its limit
    assert limit_verdict(95.0, 1.0, 40.0, 150.0) == "client"       # generator out of CPU
    assert limit_verdict(40.0, 40.0, 60.0, 150.0) == "client"      # operations issued late, no failures
    assert limit_verdict(40.0, 58.0, 30.0, 150.0, 0.21) == ""      # late only because a failing system left a backlog
    assert limit_verdict(40.0, 1.0, 60.0, 150.0) == ""
    assert limit_verdict(40.0, 1.0, None, None) == ""


def test_corrosion_error_event_is_an_error():
    import httpx
    def h(req):
        return httpx.Response(200, text='{"error":"no such table"}\n')
    a = _mock(adapters.Corrosion("http://x"), h)
    try:
        asyncio.run(a.execute("read", "a", None)); assert False, "must raise"
    except RuntimeError:
        pass


def test_e2_client_limited_step_is_not_counted_against_the_system():
    import importlib.util, os
    spec_ = importlib.util.spec_from_file_location("dash", os.path.join(os.path.dirname(__file__), "..", "..", "dashboard", "server.py"))
    dash = importlib.util.module_from_spec(spec_); spec_.loader.exec_module(dash)
    rows = [dict(system="optimusdb", dataset_records=10000, offered_ops_s=o, achieved_ops_s=a, p99_ms=10, error_rate=e, notes=n)
            for o, a, e, n in ((25, 25, 0, ""), (100, 100, 0, ""), (200, 120, 0.3, "client_limited=1"))]
    s = dash.analyse_e2(rows)["series"][0]
    assert s["saturation"] == 100 and s["lower_bound"] is True
    rows[2]["notes"] = ""
    s = dash.analyse_e2(rows)["series"][0]
    assert s["saturation"] == 100 and s["lower_bound"] is False


def test_report_copy_is_built_from_minimal_results(tmp_path):
    """The saved evaluation report builds from whatever results exist (here one E1 row, no logs)."""
    import importlib, os, sys
    dash = os.path.join(os.path.dirname(__file__), "..", "..", "dashboard")
    sys.path.insert(0, os.path.abspath(dash))
    import server, report_data, report_cli
    q = tmp_path / "quick"; q.mkdir()
    (q / "E1_raw.csv").write_text("run_id,system,workload,doc_size,rep,ops,errors,mean_ms,p50_ms,p95_ms,p99_ms,p999_ms,achieved_ops_s,start_utc,notes\n"
                                  "E1-optimusdb-WO-2KB-1,optimusdb,WO,2KB,1,100,0,3,3,5,9,12,49.6,x,dropped=0\n")
    server.RES, server.ARCH = str(tmp_path), str(tmp_path / "none")
    d = report_data.build("quick")
    assert d["completion"]["optimusdb"]["E1"] == 1 and d["notes"] is None
    html = report_cli.page(d)
    assert "window.REPORT_DATA" in html and "OptimusReport.render" in html and "</script>" in html


def test_worker_schedules_partition_the_single_process_sequence():
    w = workloads.Workload("WO", 100_000, "2KB", seed=4)
    one = loadgen._schedule(w.args, 50, 20, True, 1, 0, 1)
    parts = [loadgen._schedule(w.args, 50, 20, True, 1, i, 3) for i in range(3)]
    merged = sorted((x for p in parts for x in p), key=lambda x: x[0])
    assert [(t, k, key) for t, (k, key, _) in merged] == [(t, k, key) for t, (k, key, _) in one]
    assert [p for _, (_, _, p) in merged] == [p for _, (_, _, p) in one]      # same update/insert documents
    assert max(len(p) for p in parts) - min(len(p) for p in parts) <= 1


def _kv_server():
    import json, threading
    from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
    doc = json.dumps({"_id": "x", "p": "a" * 1900}).encode(); many = json.dumps({"results": [{"_id": "x"}] * 50}).encode()
    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        def log_message(self, *a): pass
        def _send(self, b):
            self.send_response(200); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
        def do_GET(self): self._send(doc)
        def do_PUT(self): self.rfile.read(int(self.headers["Content-Length"])); self._send(b"{}")
        def do_POST(self): self.rfile.read(int(self.headers["Content-Length"])); self._send(many)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def test_multi_process_generator_issues_the_same_operations():
    srv = _kv_server()
    try:
        cfg = {"type": "http", "base_url": f"http://127.0.0.1:{srv.server_port}", "name": "kv"}
        wl = workloads.Workload("WO", 1000, "2KB", seed=2)
        recs, dropped, info = asyncio.run(loadgen.run_open_loop_mp(cfg, wl.args, 40, 3, 0.5, workers=3))
        exp = [(t, k) for t, (k, _, _) in loadgen._schedule(wl.args, 40, 3.5, True, 1, 0, 1) if t >= 0.5]
        assert [(round(r.scheduled, 4), r.kind) for r in recs] == [(round(t, 4), k) for t, k in exp]
        assert dropped == 0 and all(r.ok for r in recs) and info["workers"] == 3 and len(info["worker_cpu"]) == 3
        assert all(r.latency_ms >= r.service_ms >= 0 for r in recs)
        q = [r for r in recs if r.kind == "query"]; assert q and all(r.rows == 50 for r in q)
    finally:
        srv.shutdown()


def test_timed_run_uses_workers_only_for_rebuildable_adapters():
    from bench import runner
    cfg = {"run": {"client_workers": 4}}
    http = adapters.make({"type": "http", "base_url": "http://x", "name": "kv"}); wl = workloads.Workload("WO", 10)
    assert runner.client_workers(cfg, http, wl) == 4
    assert runner.client_workers(cfg, adapters.InMemory(), wl) == 1
    assert runner.client_workers({"run": {"client_workers": 1}}, http, wl) == 1
    class Wrap: pass
    assert runner.client_workers(cfg, Wrap(), wl) == 1


def _odb_server(with_doc):
    import json, threading
    from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
    seen = []
    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        def log_message(self, *a): pass
        def _send(self, code, b, ctype="application/json"):
            self.send_response(code); self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
        def do_GET(self):
            seen.append(("GET", self.path))
            if with_doc and self.path.startswith("/swarmkb/doc/"):
                self._send(200, json.dumps({"status": 200, "data": [{"_id": "k1"}]}).encode())
            else:
                self._send(404, b"404 page not found\n", "text/plain")
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen.append(("POST", body["criteria"]))
            self._send(200, json.dumps({"status": 200, "data": [{"_id": "k1"}]}).encode())
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, seen


def test_optimusdb_reads_use_get_doc_and_fall_back_on_older_builds():
    for with_doc in (True, False):
        srv, seen = _odb_server(with_doc)
        try:
            ad = adapters.make({"type": "optimusdb", "base_url": f"http://127.0.0.1:{srv.server_port}", "strategy": "LOCAL_ONLY"})
            async def go():
                await ad.open()
                try: return [await ad.execute("read", "k1", None) for _ in range(3)]
                finally: await ad.close()
            assert asyncio.run(go()) == [1, 1, 1]
            gets = [p for m, p in seen if m == "GET"]; posts = [p for m, p in seen if m == "POST"]
            if with_doc:
                assert len(gets) == 3 and not posts and gets[0] == "/swarmkb/doc/k1?dstype=dsswres&strategy=LOCAL_ONLY"
            else:
                assert len(gets) == 1 and posts == [[{"_id": "k1"}]] * 3      # detected once, then the query command
        finally:
            srv.shutdown()


def test_static_site_snapshot(tmp_path):
    """tools/build_site.py writes the dashboard plus JSON answers for each result set, under the names app.js reads."""
    import json, os, subprocess, sys
    res = tmp_path / "results"; q = res / "quick"; (q / "ops").mkdir(parents=True); (res / "logs").mkdir()
    (q / "E1_raw.csv").write_text("run_id,system,workload,doc_size,rep,ops,errors,mean_ms,p50_ms,p95_ms,p99_ms,p999_ms,achieved_ops_s,start_utc,notes\n"
                                  "E1-optimusdb-WO-2KB-1,optimusdb,WO,2KB,1,2,0,3,3,5,9,12,49.6,x,dropped=0\n")
    (q / "ops" / "E1-optimusdb-WO-2KB-1.csv").write_text("scheduled_s,start_s,end_s,latency_ms,service_ms,kind,ok,rows,error\n0.1,0.1,0.103,3,3,read,1,1,\n0.2,0.2,0.205,5,5,query,1,9,\n")
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    out = tmp_path / "site"
    r = subprocess.run([sys.executable, os.path.join(root, "tools", "build_site.py"), "--results", str(res), "--archive", str(tmp_path / "arch"), "--out", str(out)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    d = out / "site-data"
    assert (out / "index.html").read_text().count("window.ODB_STATIC") == 1 and (out / ".nojekyll").exists()
    assert json.loads((d / "results" / "quick.json").read_text())["completion"]["optimusdb"]["E1"] == 1
    assert json.loads((d / "report" / "quick.json").read_text())["meta"]["label"]
    assert json.loads((d / "ops" / "quick" / "E1-optimusdb-WO-2KB-1.json").read_text())["n"] == 2
    assert [s["id"] for s in json.loads((d / "progress.json").read_text())["sources"]] == ["quick"]
