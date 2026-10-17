"""Experiment runner: `python -m bench.runner E1 --config config/testbed.yaml`.

Each experiment writes results/<E>_raw.csv with exactly the columns of sheet <E>_raw
in OptimusDB_Section8_Evidence.xlsx (see bench/spec.py) plus per-operation logs
under results/ops/ for later CDFs and re-analysis.
"""
import argparse, asyncio, csv, datetime as dt, itertools, json, os, random, re, sys, time, uuid
import yaml

from . import spec, adapters as A, faults, observe
from .workloads import expected_rows, Workload, make_doc, key_of
from .loadgen import run_open_loop, run_open_loop_mp, write_ops_csv
from .metrics import run_summary

RES = os.environ.get("BENCH_RESULTS", "results")


def now(): return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


class Sink:
    """Append-only CSV with the experiment's raw columns (resumable: existing run_ids are skipped)."""
    def __init__(self, name, cols):
        os.makedirs(RES, exist_ok=True); os.makedirs(f"{RES}/ops", exist_ok=True)
        self.path, self.cols = f"{RES}/{name}_raw.csv", cols
        self.done, self.rows = set(), {}
        if os.path.exists(self.path):
            with open(self.path) as f: self.rows = {r[cols[0]]: r for r in csv.DictReader(f)}
            self.done = set(self.rows)
        else:
            with open(self.path, "w", newline="") as f: csv.writer(f).writerow(cols)

    def write(self, row):
        with open(self.path, "a", newline="") as f:
            csv.writer(f).writerow([row.get(c, "") for c in self.cols])
        rid = str(row.get(self.cols[0], "")); self.done.add(rid); self.rows[rid] = {c: str(row.get(c, "")) for c in self.cols}


def say(msg):
    """Progress line in the experiment log (results/logs/<E>-<time>.log)."""
    print(f"{dt.datetime.now().strftime('%H:%M:%S')} {msg}", flush=True)


def log_failure(run_id, ex):
    """A failed run is logged and skipped (not written to the raw CSV), so a resumed campaign retries it."""
    import traceback
    os.makedirs(RES, exist_ok=True)
    with open(f"{RES}/failures.log", "a") as f:
        f.write(f"{now()} {run_id} {type(ex).__name__}: {ex}\n")
    print(f"[FAILED] {run_id}: {type(ex).__name__}: {ex}", file=sys.stderr)


def cfg_load(path):
    with open(path) as f: return yaml.safe_load(f)


def nodes_from(cfg):
    if "cluster" in cfg:                       # Docker Desktop multi-host deployment (host agents on the overlay)
        from . import cluster
        return cluster.nodes(cfg)
    return [faults.Node(**n) for n in cfg.get("nodes", [])]


def system_adapter(cfg, sysid, **over):
    c = dict(cfg["systems"][sysid]); c.update(over); return A.make(c)


OPENDHT_MAX_VALUE = 64 * 1024      # bytes, opendht/value.h MAX_VALUE_SIZE


def doc_bytes(size):
    from .workloads import SIZE_BYTES
    return SIZE_BYTES[size]


def records_for(cfg, size):
    """Records for a document size. The dataset volume is capped at records x 8 KB (default 10^5 x 8 KB ~ 800 MB per
    replica), so 64 KB documents use 12,500 records. Without the cap a 64 KB dataset would be 6.4 GB on every host,
    beyond the memory of in-memory stores (OpenDHT) and the disk of a single-machine testbed."""
    from .workloads import SIZE_BYTES
    records = cfg["data"]["records"]
    cap = cfg["data"].get("max_bytes", records * 8192)
    return max(1, min(records, cap // SIZE_BYTES[size]))


async def preload(ad, records, size):
    t0 = time.time(); say(f"  loading {records} records ({size})")
    docs = [make_doc(i, size) for i in range(records)]
    await ad.load(docs)
    say(f"  loaded in {time.time() - t0:.0f} s")


async def wait_replicated(cfg, sysid, records, tier=None, timeout_s=None, sample=200, poll_s=5):
    """Wait until a fixed random sample of preloaded keys is readable on every replica of `sysid` (local reads).
    Returns seconds waited, or None if the timeout passed first."""
    if "cluster" not in cfg:
        return 0.0
    from . import cluster
    timeout_s = timeout_s or cfg.get("settle_timeout_s", 900)
    keys = [key_of(i) for i in random.Random(records).sample(range(records), min(sample, records))]
    reps = []
    for h in cluster.hosts_of(cfg, tier):
        c = dict(cfg["systems"][sysid]); c["base_url"] = cluster.url(h, sysid)
        if sysid == "optimusdb": c["strategy"] = "LOCAL_ONLY"
        reps.append(A.make(c))
    for a in reps: await a.open()
    pending = {i: set(keys) for i in range(len(reps))}
    t0 = time.time()
    try:
        while time.time() - t0 < timeout_s:
            for i, a in enumerate(reps):
                todo = list(pending[i])
                res = await asyncio.gather(*(a.execute("read", k, None) for k in todo), return_exceptions=True)
                pending[i] -= {k for k, r in zip(todo, res) if not isinstance(r, Exception) and r}
            if not any(pending.values()):
                return time.time() - t0
            await asyncio.sleep(poll_s)
        hosts = cluster.hosts_of(cfg, tier)
        say("  readable sample keys per host: " + ", ".join(f"{h['name']} {len(keys) - len(pending[i])}/{len(keys)}" for i, h in enumerate(hosts)))
        return None
    finally:
        for a in reps: await a.close()


async def preload_settled(cfg, sysid, ad, records, size, tier=None, extra=None):
    """Preload on an unshaped network, wait until the data is on every replica, then re-apply the link profiles.
    The preload is not measured; loading it through the emulated WAN only made runs slower and, for some systems,
    stalled their replication (Iroh docs). Every measured window therefore starts from a fully replicated dataset.
    Returns (seconds until replicated or None, note for the CSV)."""
    shaped = "cluster" in cfg and "links" in cfg
    if shaped:
        from . import cluster
        nodes = cluster.nodes(cfg); faults.clear_netem(nodes)
    try:
        await preload(ad, records, size)
        if extra: await extra()
        settled = await wait_replicated(cfg, sysid, records, tier)
    finally:
        if shaped:
            faults.apply_netem(nodes, cluster.links(cfg))
    if settled is None:
        say(f"  WARNING: sample not readable on every replica after {cfg.get('settle_timeout_s', 900)} s; measuring anyway")
        return None, "settled=timeout"
    say(f"  replicated on every host after {settled:.0f} s")
    return settled, f"settled={settled:.0f}s"


def interleaved(cells, reps, seed):
    """Randomised, interleaved order of (cell, rep): spreads temporal noise across systems (principle P1)."""
    order = [(c, r) for r in range(1, reps + 1) for c in cells]
    random.Random(seed).shuffle(order)
    for i, (c, r) in enumerate(order, 1):
        say(f"[{i}/{len(order)}] {' '.join(map(str, c if isinstance(c, tuple) else (c,)))} rep {r}")
        yield c, r


# ---------------------------------------------------------------- is the load generator, or the system, the limit?
# The load generator is one Python process (one event loop). If it runs out of CPU it issues operations late and
# every system looks slow, which happened in quick run 4 at 200 ops/s (operations issued a median 35-43 ms late,
# against about 1 ms normally). Each load-driven run therefore records the generator's CPU and issue lag and the
# target node's CPU, and says which side was the limit.
CLIENT_CPU_LIMIT = 85.0     # % of one core
CLIENT_LAG_P50_MS = 10.0    # median delay between an operation's scheduled time and its issue
NODE_JS = {"gun", "autobase"}


def _target_host(cfg, ad):
    if "cluster" not in cfg: return None
    from . import cluster
    base = getattr(ad, "base", "") or ""
    hosts = cluster.hosts_of(cfg)
    return next((h for h in hosts if f"//{h['ip']}:" in base or f"//{h['ip']}/" in base), hosts[0] if hosts else None)


async def _sample_cpu(cfg, sysid, host, stop, out):
    from . import cluster
    ag = cluster.Agents(cfg)
    try:
        while not stop.is_set():
            try:
                st = await ag.call(host, "GET", f"/stats/odb-{host['name']}-{sysid}")
                if st.get("cpu_pct") is not None: out.append(float(st["cpu_pct"]))
            except Exception:  # noqa: BLE001
                pass
            try: await asyncio.wait_for(stop.wait(), 3)
            except asyncio.TimeoutError: pass
    finally:
        await ag.close()


def limit_verdict(client_cpu, lag_p50, node_cpu, node_limit, error_rate=0.0):
    """'node' when the target node's CPU was at its limit, 'client' when the load generator was, else ''.

    The generator counts as the limit when it used most of its core, or when it issued operations late in a run
    without failures. A late issue during a failing run is not enough on its own: a system that falls behind
    leaves thousands of outstanding requests, and handling them slows the client too (quick run 5: OpenDHT at
    100 ops/s was marked client-limited by the issue delay alone)."""
    if node_cpu is not None and node_limit and node_cpu >= 0.85 * node_limit: return "node"
    if client_cpu is not None and client_cpu >= CLIENT_CPU_LIMIT: return "client"
    if lag_p50 is not None and lag_p50 > CLIENT_LAG_P50_MS and (error_rate or 0) <= 0.01: return "client"
    return ""


def client_workers(cfg, ad, wl):
    """Load-generator processes for a timed run: run.client_workers (default 4). Adapters built from a config and
    workloads built from their arguments can be rebuilt in a worker; wrappers (E5 acknowledgements, E6 trace) and
    test doubles stay in one process."""
    n = int((cfg.get("run") or {}).get("client_workers", 4) or 1)
    if n <= 1 or not getattr(ad, "spec", None) or not getattr(wl, "args", None): return 1
    if ad.spec.get("type") == "inmemory" or ad.spec.get("credential"): return 1
    return n


async def timed_run(ad, wl, rate, cfg, tag, sysid=None):
    dur, warm = cfg["run"]["duration_s"], cfg["run"]["warmup_s"]
    say(f"  measuring: {warm} s warm-up + {dur} s at {rate} ops/s")
    host = _target_host(cfg, ad) if sysid else None
    stop, cpu = asyncio.Event(), []
    smp = asyncio.create_task(_sample_cpu(cfg, sysid, host, stop, cpu)) if host else None
    c0, w0 = time.process_time(), time.time()
    nw = client_workers(cfg, ad, wl)
    try:
        if nw > 1:
            recs, dropped, info = await run_open_loop_mp(ad.spec, wl.args, rate, dur, warm,
                                                         poisson=cfg["run"].get("poisson", True), workers=nw)
            client_cpu = max(info["worker_cpu"])     # the busiest worker; each has a core of its own
        else:
            recs, dropped = await run_open_loop(ad, wl, rate, dur, warm, poisson=cfg["run"].get("poisson", True))
            client_cpu = None
    finally:
        stop.set()
        if smp: await smp
    if client_cpu is None: client_cpu = round(100.0 * (time.process_time() - c0) / max(1e-6, time.time() - w0), 1)
    write_ops_csv(f"{RES}/ops/{tag}.csv", recs)
    s = run_summary(recs, dur); s["dropped"] = dropped
    lag = sorted((r.start - r.scheduled) * 1000.0 for r in recs)
    lag50 = round(lag[len(lag) // 2], 1) if lag else None
    lag99 = round(lag[min(len(lag) - 1, int(0.99 * len(lag)))], 1) if lag else None
    node_cpu = round(max(cpu), 1) if cpu else None
    node_limit = None
    if host and host.get("cpus"):
        node_limit = float(host["cpus"]) * 100
        if sysid in NODE_JS: node_limit = min(node_limit, 100.0)
    er = (s.get('errors') or 0) / s['ops'] if s.get('ops') else 0.0
    v = limit_verdict(client_cpu, lag50, node_cpu, node_limit, er)
    s["limits"] = dict(client_cpu=client_cpu, lag_p50=lag50, lag_p99=lag99, node_cpu=node_cpu, node_limit=node_limit, verdict=v)
    s["limit_note"] = (f"client_cpu={client_cpu} lag_p50={lag50} lag_p99={lag99} workers={nw}"
                       + (f" node_cpu={node_cpu}/{node_limit:.0f}" if node_cpu is not None and node_limit else "")
                       + (" client_limited=1" if v == "client" else " node_cpu_bound=1" if v == "node" else ""))
    say(f"  done {tag}: ops={s.get('ops')} errors={s.get('errors')} p50={s.get('p50_ms')} ms p99={s.get('p99_ms')} ms"
        + (f" unsupported={s['unsupported']}" if s.get("unsupported") else "")
        + f" | load generator CPU {client_cpu} %" + (f" (busiest of {nw} workers)" if nw > 1 else "") + f", issue lag p50 {lag50} ms"
        + (f", {host['name']} CPU max {node_cpu} % of {node_limit:.0f} %" if node_cpu is not None and node_limit else ""))
    if v == "client":
        say(f"  WARNING: the load generator was the limit in {tag} (CPU {client_cpu} %, issue lag p50 {lag50} ms): "
            "this run measures the client, not the system; it is marked client_limited")
    return s


# ---------------------------------------------------------------- profiles
# "quick" runs every common scenario once on small data in about two hours: a first look and an end-to-end check.
# It has one repetition, so it gives no confidence intervals or significance tests; the paper uses the full campaign.
QUICK = dict(e1_sizes=[], e2_sizes=[(10_000, [25, 100, 200])], e2_window=(10, 30), e2_pause=5,
             e3_sizes=[10_000], e3_iters=(2, 20), e4_levels=[0, 40], e4_window=45, e5_conv_timeout=120,
             e5_cells=[("optimusdb", 0, 30, "4|4"), ("optimusdb", 30, 30, "4|4")] +
                      [(b, 30, 30, "4|4") for b in ("corrosion", "gun", "autobase", "iroh", "opendht")])


def quick(cfg): return cfg.get("profile") == "quick"


# ---------------------------------------------------------------- load once, run many (YCSB load / run phases)
def block_order(blocks, seed):
    """blocks: list of (key, runs). Block order and run order inside each block are shuffled (fixed seed).
    Each block is one deployment + one preload; all its runs follow on that data."""
    rng = random.Random(seed)
    blocks = [(k, list(r)) for k, r in blocks]
    rng.shuffle(blocks)
    for _, runs in blocks: rng.shuffle(runs)
    return blocks


def _cell_text(c):
    return " ".join(map(str, c if isinstance(c, tuple) else (c,)))


# ======================================================================== E1
async def e1(cfg, args):
    e = next(x for x in spec.EXPERIMENTS if x["id"] == "E1"); sink = Sink("E1", e["raw"])
    systems = args.systems or list(cfg["systems"])
    reps = range(1, (args.reps or e["reps"]) + 1)
    sizes = QUICK["e1_sizes"] if quick(cfg) else ["8KB"] if getattr(args, "pilot", False) else ["256B", "8KB", "64KB"]
    blocks = []
    wls = [w for w in ["WA", "WB", "WC", "WO"] if w in (getattr(args, "workloads", None) or ["WA", "WB", "WC", "WO"])]
    for s in systems:
        if wls: blocks.append(((s, "2KB"), [((s, w, "2KB"), r) for w in wls for r in reps]))
        if "WO" in wls: blocks += [((s, sz), [((s, "WO", sz), r) for r in reps]) for sz in sizes]    # document-size series
    order = block_order(blocks, cfg.get("seed", 1))
    total = sum(len(r) for _, r in order); i = 0
    for b, ((sysid, size), runs) in enumerate(order, 1):
        todo = [(c, r) for c, r in runs if f"E1-{c[0]}-{c[1]}-{c[2]}-{r}" not in sink.done]
        if not todo:
            i += len(runs); continue
        i += len(runs) - len(todo)
        nrec = records_for(cfg, size)
        if sysid == "opendht" and doc_bytes(size) >= OPENDHT_MAX_VALUE:   # JSON adds bytes above the nominal size
            # OpenDHT rejects values above 64 KiB (MAX_VALUE_SIZE in opendht/value.h): the cell is not runnable.
            say(f"== block {b}/{len(order)}: {sysid} {size} skipped: above OpenDHT's 64 KiB value limit")
            for (sid, wl_id, sz), rep in todo:
                sink.write(dict(run_id=f"E1-{sid}-{wl_id}-{sz}-{rep}", system=sid, workload=wl_id, doc_size=sz, rep=rep,
                                notes="unsupported: document above OpenDHT's 64 KiB value limit"))
            continue
        say(f"== block {b}/{len(order)}: {sysid} {size}, {nrec} records, {len(todo)} runs on one preload")
        ad = system_adapter(cfg, sysid); await ad.open()
        loaded, snote, seq = False, "", 0
        try:
            for (sid, wl_id, sz), rep in todo:
                i += 1; seq += 1
                run_id = f"E1-{sid}-{wl_id}-{sz}-{rep}"
                say(f"[{i}/{total}] {sid} {wl_id} {sz} rep {rep}")
                try:
                    if not loaded:
                        await cfg_reset(cfg, sysid); await renew(ad); _, snote = await preload_settled(cfg, sysid, ad, nrec, size)
                        loaded, seq = True, 1
                    elif (down := await down_hosts(cfg, sysid)):
                        say(f"  {sysid} not answering on {', '.join(down)}: redeploying and reloading before this run")
                        await cfg_reset(cfg, sysid); await renew(ad); _, snote = await preload_settled(cfg, sysid, ad, nrec, size)
                        seq = 1
                    wl = Workload(wl_id, nrec, sz, seed=rep)
                    t = now(); s = await timed_run(ad, wl, cfg["run"]["rate"], cfg, run_id, sysid)
                    uns = f" unsupported={s['unsupported']}" if s.get("unsupported") else ""
                    died = await down_hosts(cfg, sysid)
                    dn = f" node_down_after_run={'+'.join(died)}" if died else ""
                    if died:
                        say(f"  WARNING: {sysid} stopped answering on {', '.join(died)} during {run_id}")
                        await save_node_logs(cfg, sysid, died, run_id)
                    lim = s.pop("limits", None); ln = s.pop("limit_note", "")
                    sink.write(dict(run_id=run_id, system=sid, workload=wl_id, doc_size=sz, rep=rep, start_utc=t,
                                    notes=f"dropped={s['dropped']} records={nrec} {snote} seq={seq}{uns}{dn} {ln}".strip(), **s))
                    if died: loaded = False
                    elif s.get("ops") and s["errors"] / s["ops"] > 0.2:
                        # a saturated run leaves a backlog (queued requests, pending replication) that would distort the
                        # next run of the block, which was seen with Gun.js (WA failing only after WO): start it fresh
                        say(f"  {100 * s['errors'] / s['ops']:.0f} % errors: redeploying before the next run of this block")
                        loaded = False
                except Exception as ex:  # noqa: BLE001 - keep the campaign running; reload before the next run
                    log_failure(run_id, ex); loaded = False
        finally:
            await ad.close()


# ======================================================================== E2
async def e2(cfg, args):
    e = next(x for x in spec.EXPERIMENTS if x["id"] == "E2"); sink = Sink("E2", e["raw"])
    systems = args.systems or list(cfg["systems"])
    reps = list(range(1, (args.reps or e["reps"]) + 1))
    sizes = [(100_000, list(range(10, 210, 10)))] + [(n, [50]) for n in spec.DATASET_SIZES if n != 100_000]
    if quick(cfg): sizes = QUICK["e2_sizes"]
    order = block_order([((s, n, tuple(loads)), reps) for s in systems for n, loads in sizes], cfg.get("seed", 1))
    warm, dur = QUICK["e2_window"] if quick(cfg) else (30, 180)
    window = dict(cfg, run=dict(cfg["run"], duration_s=dur, warmup_s=warm))
    pause = QUICK["e2_pause"] if quick(cfg) else 30
    def saturated(run_id, rate):
        row = sink.rows.get(run_id)
        m = re.search(r"supported_share=([\d.]+)", (row or {}).get("notes") or "")
        try: return row is not None and float(row["achieved_ops_s"]) < 0.9 * rate * (float(m.group(1)) if m else 1.0)
        except (TypeError, ValueError): return False

    def rep_done(sysid, records, loads, rep):
        for rate in loads:
            rid = f"E2-{sysid}-{records}-{rate}-{rep}"
            if rid not in sink.done: return False
            if len(loads) > 1 and saturated(rid, rate): return True
        return True

    for b, ((sysid, records, loads), rep_order) in enumerate(order, 1):
        if all(rep_done(sysid, records, loads, rep) for rep in rep_order): continue
        say(f"[{b}/{len(order)}] E2 block {sysid} {records} records: load once, {len(rep_order)} repetitions")
        ad = system_adapter(cfg, sysid); await ad.open()
        loaded = False
        try:
            for rep in sorted(rep_order):
                if rep_done(sysid, records, loads, rep): continue
                try:
                    if not loaded:
                        await cfg_reset(cfg, sysid); await renew(ad); await preload_settled(cfg, sysid, ad, records, "2KB"); loaded = True
                    for rate in loads:
                        run_id = f"E2-{sysid}-{records}-{rate}-{rep}"
                        if run_id in sink.done:
                            if len(loads) > 1 and saturated(run_id, rate): break
                            continue
                        if (down := await down_hosts(cfg, sysid)):
                            say(f"  {sysid} not answering on {', '.join(down)}: redeploying and reloading")
                            await cfg_reset(cfg, sysid); await renew(ad); await preload_settled(cfg, sysid, ad, records, "2KB")
                        s = await timed_run(ad, Workload("WO", records, "2KB", seed=rep), rate, window, run_id, sysid)
                        er = s["errors"] / s["ops"] if s["ops"] else 1.0
                        died = await down_hosts(cfg, sysid)
                        if died:
                            say(f"  WARNING: {sysid} stopped answering on {', '.join(died)} during {run_id}")
                            await save_node_logs(cfg, sysid, died, run_id)
                        row = dict(run_id=run_id, system=sysid, dataset_records=records, offered_ops_s=rate, rep=rep,
                                   achieved_ops_s=s["achieved_ops_s"], p99_ms=s["p99_ms"], error_rate=round(er, 5))
                        share = s.get("supported_share", 1.0)
                        lim = s.get("limits") or {}
                        if "bottleneck" in sink.cols:
                            row["bottleneck"] = {"node": "node CPU", "client": "load generator"}.get(lim.get("verdict"), "")
                        if "notes" in sink.cols:
                            row["notes"] = " ".join(x for x in (f"node_down_after_run={'+'.join(died)}" if died else "",
                                                               f"supported_share={share}" if share < 1 else "",
                                                               s.get("limit_note", "")) if x)
                        sink.write(row)
                        if s["achieved_ops_s"] < 0.9 * rate * share and len(loads) > 1:
                            break   # past saturation: stop stepping this repetition
                    await asyncio.sleep(pause)   # let a saturated system drain before the next repetition
                except Exception as ex:  # noqa: BLE001
                    log_failure(f"E2-{sysid}-{records}-rep{rep}", ex); loaded = False
        finally:
            await ad.close()


# ======================================================================== E3
# Paths answered by a SQL engine. "crdt" (OptimusDB's document query on the CRDT store) is not one of them: it
# uses the criteria query natively, including range operators (Q3), and evaluates what criteria cannot express
# (GROUP BY, joins) in the client.
SQL_PATHS = ("sqlite", "sql")


async def client_eval(ad, qid, point_key):
    """Q1-Q5 evaluated by the application over a system without a query language (row count returned).
    Raises NotImplementedError where the interface cannot enumerate data (OpenDHT beyond Q1)."""
    if qid == "Q1":
        r = await ad.execute("read", point_key, None)
        return 1 if r else 0
    if qid == "Q2":
        return len(await ad.query({"status": "Running"}))
    if qid == "Q3":
        if getattr(ad, "native_ops", False):    # the system evaluates the ranges itself, as SQL does for Corrosion
            return len(await ad.query({"region": "eu-west", "cpu_capacity": {"$gte": 4}, "memory_capacity": {"$gte": 8192}}))
        return sum(1 for d in await ad.query({"region": "eu-west"}) if d.get("cpu_capacity", 0) >= 4 and d.get("memory_capacity", 0) >= 8192)
    docs = await ad.query({})
    if qid == "Q4":
        groups = {}
        for d in docs:
            if d.get("type") == "allocation": continue
            g = groups.setdefault(d.get("region"), [0, 0.0]); g[0] += 1; g[1] += d.get("cpu_capacity", 0)
        return len(groups)
    if qid == "Q5":
        res = {d["_id"] for d in docs if d.get("type") != "allocation" and d.get("region") == "eu-west"}
        return sum(1 for d in docs if d.get("type") == "allocation" and d.get("resource_id") in res)
    raise ValueError(qid)


async def e3(cfg, args):
    """Queries are read-only, so all repetitions of a (target, dataset) block run on one preload."""
    import numpy as np
    e = next(x for x in spec.EXPERIMENTS if x["id"] == "E3"); sink = Sink("E3", e["raw"])
    targets = cfg["e3_targets"]          # list of {system, path, override}
    if args.systems: targets = [t for t in targets if t["system"] in args.systems]
    reps = list(range(1, (args.reps or e["reps"]) + 1))
    sizes = QUICK["e3_sizes"] if quick(cfg) else [10_000, 100_000, 1_000_000]
    warm_q, meas_q = QUICK["e3_iters"] if quick(cfg) else (20, 200)
    blocks = [((ti, records), reps) for ti in range(len(targets)) for records in sizes]
    order = block_order(blocks, cfg.get("seed", 1))
    ref = cfg.get("e3_reference") or {}
    for b, ((ti, records), rep_order) in enumerate(order, 1):
        t = targets[ti]
        ids = [f"E3-{t['system']}-{t['path']}-{q}-{records}-{r}" for r in rep_order for q, _, _ in spec.QUERIES]
        if all(x in sink.done for x in ids): continue
        say(f"[{b}/{len(order)}] E3 block {t['system']} {t['path']} {records} records: load once, {len(rep_order)} repetitions")
        ad = system_adapter(cfg, t["system"], **t.get("override", {})); await ad.open()
        try:
            allocs = [{"_id": f"alloc{i}", "type": "allocation", "resource_id": key_of(i % records), "app": f"app{i % 50}"} for i in range(10_000)]
            try:
                await cfg_reset(cfg, t["system"]); await renew(ad)
                await preload_settled(cfg, t["system"], ad, records, "2KB", extra=lambda: ad.load_allocations(allocs))
            except Exception as ex:  # noqa: BLE001
                log_failure(f"E3-{t['system']}-{t['path']}-{records}-load", ex); continue
            for rep in sorted(rep_order):
                for qid, _, sql in spec.QUERIES:
                    run_id = f"E3-{t['system']}-{t['path']}-{qid}-{records}-{rep}"
                    if run_id in sink.done: continue
                    stmt = sql.replace("?", "'eu-west'").replace("id = 'eu-west'", f"id = '{key_of(records // 2)}'")
                    lat, rows, ok, note = [], -1, True, ""
                    try:
                        for i in range(warm_q + meas_q):
                            t0 = time.perf_counter()
                            if t["path"] in SQL_PATHS: rows = await ad.sql(stmt)
                            else: rows = await client_eval(ad, qid, key_of(records // 2))
                            if i >= warm_q: lat.append((time.perf_counter() - t0) * 1000)
                    except NotImplementedError:
                        ok = False; note = "unsupported"; lat = []
                    except Exception as ex:  # noqa: BLE001
                        ok = False; lat = []; note = f"failed: {type(ex).__name__}: {str(ex)[:80]}"
                        log_failure(run_id, ex)
                    exp = ref.get(f"{qid}:{records}")
                    if exp is None: exp = expected_rows(qid, records)
                    sink.write(dict(run_id=run_id, system=t["system"], path=t["path"], query=qid, dataset_records=records, rep=rep,
                                    mean_ms=round(float(np.mean(lat)), 3) if lat else "", p95_ms=round(float(np.percentile(lat, 95)), 3) if lat else "",
                                    rows_returned=rows, rows_expected=exp, correct=int(ok and rows == exp),
                                    notes=note))
                say(f"  done E3 {t['system']} {t['path']} {records} rep {rep}")
        finally:
            await ad.close()


# ======================================================================== E4
async def e4(cfg, args):
    """One edge deployment and preload per system; all levels and repetitions follow on it."""
    e = next(x for x in spec.EXPERIMENTS if x["id"] == "E4"); sink = Sink("E4", e["raw"])
    edge = [n for n in nodes_from(cfg) if n.tier == "edge"]
    systems = list(args.systems or cfg.get("edge_systems", list(cfg["systems"])))
    reps = list(range(1, (args.reps or e["reps"]) + 1))
    order = block_order([(s, reps) for s in systems], cfg.get("seed", 1))
    levels = QUICK["e4_levels"] if quick(cfg) else [0, 10, 20, 40]
    secs = QUICK["e4_window"] if quick(cfg) else 300
    window = dict(cfg, run=dict(cfg["run"], duration_s=secs, warmup_s=0))
    for b, (sysid, rep_order) in enumerate(order, 1):
        if all(f"E4-{sysid}-{r}-{rep}" in sink.done for rep in rep_order for r in levels): continue
        say(f"[{b}/{len(order)}] E4 block {sysid}: edge deployment, load once, {len(rep_order)} repetitions")
        ad = system_adapter(cfg, sysid, **cfg.get("edge_override", {}).get(sysid, {})); await ad.open()
        try:
            try:
                await cfg_reset(cfg, sysid + "_edge" if sysid + "_edge" in cfg.get("reset", {}) else sysid); await renew(ad)
                await preload_settled(cfg, sysid, ad, 10_000, "2KB", tier="edge")
            except Exception as ex:  # noqa: BLE001
                for rep in rep_order:
                    sink.write(dict(run_id=f"E4-{sysid}-0-{rep}", system=sysid, offered_ops_s=0, rep=rep, started_ok=0, notes=str(ex)[:80]))
                continue
            docs = 10_000
            for rep in sorted(rep_order):
                for rate in levels:
                    run_id = f"E4-{sysid}-{rate}-{rep}"
                    if run_id in sink.done: continue
                    say(f"  E4 {sysid} rep {rep}: {rate} ops/s for {secs} s")
                    if "cluster" in cfg:
                        samplers = [observe.sample_container(n, f"odb-{sysid}", 1.0, secs) for n in edge]
                    else:
                        samplers = [observe.sample_resources(n, cfg["process_pattern"].get(sysid, sysid), 1.0, secs) for n in edge]
                    if rate:
                        wl = Workload("WO", 10_000, "2KB", seed=rep)
                        res = await asyncio.gather(timed_run(ad, wl, rate, window, run_id), *samplers); s, samples = res[0], res[1:]
                        docs = max(docs, wl.next_insert)     # inserts add documents (same keys again in later runs)
                    else:
                        samples = await asyncio.gather(*samplers); s = {}
                    per = [observe.summarize_resources(x) for x in samples]
                    cpu = [p["cpu_pct"] for p in per if p["cpu_pct"] is not None]; rss = [p["rss_mb"] for p in per if p["rss_mb"] is not None]
                    extra = {}
                    if "cluster" in cfg:   # disk per 1,000 documents and network bytes per operation, averaged over edge nodes
                        disk = [x[-1][3] for x in samples if x and x[-1][3] is not None]
                        net = [(x[-1][4] - x[0][4]) for x in samples if len(x) > 1 and x[0][4] is not None and x[-1][4] is not None]
                        ops = s.get("ops") or 0
                        if disk: extra["disk_mb_per_1k_docs"] = round(sum(disk) / len(disk) / (docs / 1000.0), 3)
                        if net and ops: extra["net_kb_per_op"] = round(sum(net) / len(net) / 1024.0 / ops, 3)
                    sink.write(dict(run_id=run_id, system=sysid, offered_ops_s=rate, rep=rep, started_ok=1,
                                    cpu_pct=round(sum(cpu) / len(cpu), 2) if cpu else "", rss_mb=round(sum(rss) / len(rss), 1) if rss else "",
                                    notes=f"documents={docs}; power: no meter", **extra))
        finally:
            await ad.close()

async def down_hosts(cfg, sysid, timeout_s=20):
    """Hosts whose node of `sysid` does not answer its readiness probe (empty list: all alive). A node that died
    during a run used to stay dead for the rest of the block, so every later run measured only connection errors."""
    from . import cluster as C
    try:
        hosts = C.hosts_of(cfg)
    except Exception:  # noqa: BLE001  (multi-host configs without cluster section)
        return []
    down = []
    for h in hosts:
        try:
            await C.wait_ready(sysid, [h], timeout_s=timeout_s)
        except TimeoutError:
            down.append(h["name"])
        except Exception:  # noqa: BLE001
            down.append(h["name"])
    return down


async def save_node_logs(cfg, sysid, names, run_id, tail=300):
    """Keep the last lines of the container log of nodes that stopped answering (results/<mode>/node-logs/), so the
    cause (crash, out of memory, exception) is not lost when the testbed redeploys the system."""
    from . import cluster as C
    ag = C.Agents(cfg)
    try:
        os.makedirs(f"{RES}/node-logs", exist_ok=True)
        for h in C.hosts_of(cfg):
            if h["name"] not in names: continue
            try:
                r = await ag.call(h, "GET", f"/logs/{sysid}?tail={tail}")
                text = (r.get("stdout") or "") + (r.get("stderr") or "")
            except Exception as ex:  # noqa: BLE001
                text = f"could not read the log: {type(ex).__name__}: {ex}"
            with open(f"{RES}/node-logs/{run_id}-{h['name']}.log", "w") as f: f.write(text)
        say(f"  container logs of {', '.join(names)} saved in node-logs/")
    finally:
        await ag.close()


async def renew(ad):
    """New connections after a redeployment. Requests cancelled at the 10 s timeout while a node hung can leave the
    client's connection pool exhausted; in the pilot every later request of the block then failed with PoolTimeout
    (Autobase WA and WO 2 KB never started). A redeployed system starts with a fresh client."""
    try: await ad.close()
    except Exception: pass   # noqa: BLE001
    await ad.open()


async def cfg_reset(cfg, sysid):
    """Fresh deployment per run. Docker Desktop deployment: stop every other system, wipe this one,
    start and join it on all hosts (or only the edge hosts for `<system>_edge`) and smoke-test replication.
    Otherwise run the per-system shell hook, e.g. `make reset-optimusdb`."""
    if "cluster" in cfg:
        from . import cluster
        base, _, tier = sysid.partition("_")
        if base.startswith("optimusdb") and tier.isdigit(): base, tier = "optimusdb", ""
        say(f"  reset {sysid}: stop others, wipe, start, join, smoke test")
        await cluster.reset(cfg, base, tier or None)
        return
    hook = cfg["systems"][sysid].get("reset") if isinstance(cfg["systems"][sysid], dict) else None
    hook = hook or cfg.get("reset", {}).get(sysid)
    if hook:
        p = await asyncio.create_subprocess_shell(hook); await p.wait()
        await asyncio.sleep(cfg.get("settle_s", 20))


# ======================================================================== E7
async def e7(cfg, args):
    e = next(x for x in spec.EXPERIMENTS if x["id"] == "E7"); sink = Sink("E7", e["raw"])
    inits = cfg["initiators"]   # {cloud: url, fog: url, edge: url}
    truth = None
    cells = list(itertools.product(spec.STRATEGIES, spec.TIERS, [300, 1200, 3000]))
    for (strat, tier, budget), rep in interleaved(cells, args.reps or e["reps"], cfg.get("seed", 1)):
        run_id = f"E7-{strat}-{tier}-{budget}-{rep}"
        if run_id in sink.done: continue
        ad = A.OptimusDB(inits[tier], strategy=strat, time_budget_ms=budget); await ad.open()
        try:
            if truth is None:   # ground truth = union over all replicas for the fixed query
                truth = await ground_truth(cfg)
            lat, comp = [], []
            for i in range(500):
                crit = {"region": spec.__dict__.get("E7_REGION", "eu-west"), "status": "Running"}
                t0 = time.perf_counter(); res = await ad.query(crit); lat.append((time.perf_counter() - t0) * 1000)
                ids = {d.get("_id") for d in (res if isinstance(res, list) else res.get("results", []) if isinstance(res, dict) else [])}
                comp.append(100.0 * len(ids & truth) / len(truth) if truth else 0)
            import numpy as np
            sink.write(dict(run_id=run_id, strategy=strat, initiator_tier=tier, time_budget_ms=budget, rep=rep,
                            mean_ms=round(float(np.mean(lat)), 2), p99_ms=round(float(np.percentile(lat, 99)), 2),
                            completeness_pct=round(float(np.mean(comp)), 2), notes="staleness: from analyze.py ops join"))
        finally:
            await ad.close()


async def ground_truth(cfg):
    ids = set()
    for url in cfg["agents"]:
        ad = A.OptimusDB(url, strategy="LOCAL_ONLY"); await ad.open()
        try:
            res = await ad.query({"region": "eu-west", "status": "Running"})
            ids |= {d.get("_id") for d in (res if isinstance(res, list) else res.get("results", []) if isinstance(res, dict) else [])}
        finally:
            await ad.close()
    return ids



# ======================================================================== E8
async def e8(cfg, args):
    e = next(x for x in spec.EXPERIMENTS if x["id"] == "E8"); sink = Sink("E8", e["raw"])
    for rep in range(1, (args.reps or e["reps"]) + 1):
        for agents in [4, 8, 16, 32, 64]:
            if agents not in cfg.get("agents_by_size", {}): continue
            urls = cfg["agents_by_size"][agents]
            for scaling, rate in [("weak", 10 * agents), ("strong", 80)]:
                run_id = f"E8-{agents}-{scaling}-{rep}"
                if run_id in sink.done: continue
                await cfg_reset(cfg, f"optimusdb_{agents}")
                ads = [A.OptimusDB(u) for u in urls]
                for a in ads: await a.open()
                await preload(ads[0], 100_000, "2KB")
                class Spread:   # clients spread evenly over all agents
                    i = 0
                    async def execute(s, kind, key, payload):
                        Spread.i += 1; return await ads[Spread.i % len(ads)].execute(kind, key, payload)
                s = await timed_run(Spread(), Workload("WO", 100_000, "2KB", seed=rep), rate, cfg, run_id)
                t_last = time.time(); conv, same, _ = await observe.wait_convergence(ads, t_last, 300)
                sink.write(dict(run_id=run_id, agents=agents, scaling=scaling, rep=rep, offered_ops_s=rate,
                                achieved_ops_s=s["achieved_ops_s"], mean_ms=s["mean_ms"], p99_ms=s["p99_ms"],
                                convergence_s=round(conv, 3), notes="gossip msgs and RSS from Prometheus (libp2p metrics, cAdvisor)"))
                for a in ads: await a.close()

# ======================================================================== E5
def _replica_adapters(cfg, sysid):
    """One adapter per node for `sysid` (cfg['replicas'][sysid] = list of base URLs)."""
    urls = cfg["replicas"][sysid] if sysid != "optimusdb" else cfg["agents"]
    base = dict(cfg["systems"][sysid])
    out = []
    for u in urls:
        c = dict(base); c["base_url"] = u
        if sysid == "optimusdb": c["strategy"] = "LOCAL_ONLY"
        out.append(A.make(c))
    return out


async def e5(cfg, args):
    """One deployment and preload per system; runs follow on it in random order. After every run the replicas must
    converge again; if they do not (or the run fails), the system is redeployed and reloaded before the next run."""
    e = next(x for x in spec.EXPERIMENTS if x["id"] == "E5"); sink = Sink("E5", e["raw"])
    nodes = nodes_from(cfg)
    cells = [("optimusdb",) + c for c in itertools.product([0, 5, 15, 30, 50], [5, 30, 60, 300], ["4|4", "2|6"])]
    baselines = [x[0] for x in spec.SYSTEMS if x[0] != "optimusdb"]
    cells += [(b, c, p, "4|4") for b in baselines for c in (0, 30) for p in (60, 300)]   # reduced grid for the baselines
    if quick(cfg): cells = list(QUICK["e5_cells"])
    if args.systems: cells = [c for c in cells if c[0] in args.systems]
    reps = range(1, (args.reps or e["reps"]) + 1)
    systems = list(dict.fromkeys(c[0] for c in cells))
    order = block_order([(s, [(c, r) for c in cells if c[0] == s for r in reps]) for s in systems], cfg.get("seed", 1))
    total = sum(len(r) for _, r in order); i = 0
    for b, (sysid, runs) in enumerate(order, 1):
        todo = [(c, r) for c, r in runs if f"E5-{c[0]}-{c[1]}-{c[2]}-{c[3].replace('|', 'v')}-{r}" not in sink.done]
        i += len(runs) - len(todo)
        if not todo: continue
        say(f"== block {b}/{len(order)}: {sysid}, {len(todo)} runs on one preload")
        ads = _replica_adapters(cfg, sysid)
        for a in ads: await a.open()
        fresh = False
        try:
            for (sid, cont, part_s, shape), rep in todo:
                i += 1
                run_id = f"E5-{sid}-{cont}-{part_s}-{shape.replace('|', 'v')}-{rep}"
                say(f"[{i}/{total}] {sid} {cont} {part_s} {shape} rep {rep}")
                try:
                    if not fresh:
                        await cfg_reset(cfg, sysid)
                        await preload_settled(cfg, sysid, ads[0], 10_000, "2KB")
                        # OpenDHT replicates each value to a few nodes only, so whole-replica comparison is not defined
                        # (as in e5_run); reading every key on every node also took hours through its REST proxy.
                        if sysid != "opendht":
                            conv0, same0, _ = await observe.wait_convergence(ads, time.time(), timeout_s=QUICK["e5_conv_timeout"] if quick(cfg) else 600,
                                                                             progress=say)
                            if not same0: say(f"  WARNING: replicas of {sysid} not identical after the preload ({conv0:.0f} s); running anyway")
                        fresh = True
                    row, converged = await e5_run(cfg, sysid, ads, nodes, cont, part_s, shape, rep, run_id)
                    sink.write(row)
                    if not converged and not quick(cfg): fresh = False      # redeploy before the next run (campaign only)
                except Exception as ex:  # noqa: BLE001
                    log_failure(run_id, ex); faults.heal(nodes); fresh = False
        finally:
            for a in ads: await a.close()


async def e5_run(cfg, sysid, ads, nodes, cont, part_s, shape, rep, run_id):
    k = int(shape.split("|")[0]); groups = [nodes[:k], nodes[k:]]
    hot = random.Random(rep).sample(range(10_000), 100)
    ack = observe.AckLog(side_of=lambda w: 0 if w < k else 1); tried = [0]; ok = [0]   # writer i runs on node i
    base = int(time.time() * 1000) * 1000      # versions grow across runs on the same data
    writers = [Workload("WA", 10_000, "2KB", seed=rep * 100 + i, hot_keys=hot, contention=cont / 100) for i in range(len(ads))]
    for w in writers: w.version = base

    class Acking:
        def __init__(s, ad, wid): s.ad, s.wid = ad, wid
        async def execute(s, kind, key, payload):
            if kind in ("update", "insert"):
                tried[0] += 1; payload = dict(payload, writer=s.wid)
            t_issue = time.time()
            r = await s.ad.execute(kind, key, payload)
            if kind in ("update", "insert"):
                ok[0] += 1; ack.ack(key, payload["version"], writer=s.wid, issue_ts=t_issue, ack_ts=time.time())
            return r
    faults.partition(groups)
    try:
        await asyncio.gather(*[run_open_loop(Acking(a, i), w, 50 / len(ads), part_s, 0) for i, (a, w) in enumerate(zip(ads, writers))])
    finally:
        if sysid == "opendht":
            faults.heal(nodes)
    if sysid == "opendht":     # partial replication: replica identity and convergence are not defined
        await asyncio.sleep(cfg.get("settle_s", 20)); divergent, conv, same = "", float("nan"), True
    else:
        snaps = await asyncio.gather(*(a.snapshot_hash() for a in ads), return_exceptions=True)
        divergent = len({x[0] for x in snaps if not isinstance(x, Exception)}) + sum(isinstance(x, Exception) for x in snaps)
        t_heal = faults.heal(nodes)
        say("  partition healed; waiting for the replicas to converge")
        conv, same, _ = await observe.wait_convergence(ads, t_heal, timeout_s=QUICK["e5_conv_timeout"] if quick(cfg) else 600,
                                                      progress=say)
        if not same:
            # which replicas differ, and by how many documents: tells a replica that is behind (fewer documents) from
            # one that holds different versions (same count, different hash) or a partial snapshot read
            res = await asyncio.gather(*(a.snapshot_hash() for a in ads), return_exceptions=True)
            say("  replicas not identical: " + ", ".join(
                f"{n.name}={'error ' + type(x).__name__ if isinstance(x, BaseException) else str(x[1]) + ' docs #' + str(x[0])[:6]}"
                for n, x in zip(nodes, res)))
    n_acked = len(ack.acked)
    say(f"  checking {n_acked} acknowledged keys for lost writes")
    lost, checked, unreadable = await ack.lost(ads[0], lambda a, key: a.get_doc(key), progress=say)
    loss_note = "" if checked == n_acked else f"; loss check read {checked}/{n_acked} keys ({unreadable} unreadable)"
    row = dict(run_id=run_id, system=sysid, contention_pct=cont, partition_s=part_s, partition_shape=shape, rep=rep,
               write_availability_pct=round(100.0 * ok[0] / tried[0], 2) if tried[0] else "",
               ack_writes=len(ack.acked), lost_ack_writes=lost, divergent_entries=divergent,
               convergence_s=(round(conv, 3) if conv == conv else ""), replicas_identical=(int(same) if sysid != "opendht" else ""),
               keys_readable_pct=round(100.0 * (1 - lost / max(1, checked)), 3) if checked else "",
               notes="merge_msgs from gossip metrics" + ("; partial replication: replica identity not applicable" if sysid == "opendht" else "")
                     + loss_note)
    say(f"  done {run_id}: availability={row['write_availability_pct']} lost={lost} convergence_s={row['convergence_s']}{loss_note}")
    return row, bool(same)


# ======================================================================== E9
async def e9(cfg, args):
    e = next(x for x in spec.EXPERIMENTS if x["id"] == "E9"); sink = Sink("E9", e["raw"])
    nodes = nodes_from(cfg)
    for policy in spec.ELECTION_POLICIES:
        print(f"[E9] set election policy '{policy}' on all agents (env ELECTION_POLICY; preferred-coordinator bias OFF), then press Enter");
        if not args.yes: input()
        for agents, scen, trial in itertools.product([4, 8, 16, 32], spec.FAILURE_SCENARIOS, range(1, (args.reps or e["reps"]) + 1)):
            tid = f"E9-{policy}-{agents}-{scen}-{trial}"
            if tid in sink.done: continue
            await cfg_reset(cfg, f"optimusdb_{agents}")
            urls = cfg["agents_by_size"][agents]; act = nodes[:agents]
            ad0 = A.OptimusDB(urls[0]); await ad0.open()
            _, _, leader, term, scores = observe.parse_status(await ad0.status())
            await ad0.close()
            leader_node = next((n for n, u in zip(act, urls) if leader and leader in (await status_id(u))), act[0])
            victim = leader_node if scen != "follower_crash" else next(n for n in act if n is not leader_node)
            t0 = time.time(); dead = set()
            if scen.startswith("partition"):
                minority = [leader_node] if scen.endswith("minority") else [n for n in act if n is not leader_node][: max(1, agents // 4)]
                faults.partition([minority, [n for n in act if n not in minority]])
            else:
                faults.crash(victim); dead.add(victim.name)
            live = [u for n, u in zip(act, urls) if n.name not in dead]
            elect_s, new_leader = await wait_new_leader(live, leader, t0, scen)
            avail = await availability_probe(live, 30)
            recover_s = time.time() - t0
            q = observe.quality_ratio(scores, new_leader, {await status_id(urls[act.index(victim)])} if dead else set()) if new_leader else None
            faults.heal(act); faults.restart(victim) if dead else None
            sink.write(dict(trial_id=tid, scenario=scen, agents=agents, policy=policy, detect_s="", elect_s=round(elect_s, 3) if elect_s else "",
                            recover_s=round(recover_s, 3), availability_pct=round(avail, 2), lost_ack_writes="", quality_ratio=round(q, 4) if q else "",
                            notes="detect_s from agent logs (first 'heartbeat timeout' line)"))


async def status_id(url):
    ad = A.OptimusDB(url); await ad.open()
    try: return observe.parse_status(await ad.status())[0] or ""
    except Exception: return ""
    finally: await ad.close()


async def wait_new_leader(urls, old, t0, scen, timeout=120):
    while time.time() - t0 < timeout:
        for u in urls:
            try:
                ad = A.OptimusDB(u); await ad.open(); _, _, ld, _, _ = observe.parse_status(await ad.status()); await ad.close()
                if ld and (ld != old or scen in ("follower_crash", "partition_coord_majority")):
                    return time.time() - t0, ld
            except Exception: pass
        await asyncio.sleep(0.25)
    return None, None


async def availability_probe(urls, seconds):
    ok = tot = 0; t_end = time.time() + seconds
    ads = [A.OptimusDB(u, strategy="LOCAL_THEN_REMOTE_MERGE") for u in urls]
    for a in ads: await a.open()
    while time.time() < t_end:
        a = random.choice(ads); tot += 1
        try: await a.execute("read", key_of(random.randrange(10_000)), None); ok += 1
        except Exception: pass
        await asyncio.sleep(0.05)
    for a in ads: await a.close()
    return 100.0 * ok / tot if tot else 0


# ======================================================================== E11 (scoring only)
def e11_score(gold_path, pred_path, extractor):
    """gold/pred: JSONL {doc_id, field, values:[...]} -> E11_raw rows (tp/fp/fn per doc and field, exact match after normalisation)."""
    norm = lambda v: str(v).strip().lower()
    gold = {(j["doc_id"], j["field"]): {norm(v) for v in j["values"]} for j in map(json.loads, open(gold_path))}
    pred = {(j["doc_id"], j["field"]): {norm(v) for v in j["values"]} for j in map(json.loads, open(pred_path))}
    sink = Sink("E11", next(x for x in spec.EXPERIMENTS if x["id"] == "E11")["raw"])
    for k, g in gold.items():
        p = pred.get(k, set())
        sink.write(dict(doc_id=k[0], field=k[1], extractor=extractor, tp=len(g & p), fp=len(p - g), fn=len(g - p)))


EXPS = {"E1": e1, "E2": e2, "E3": e3, "E4": e4, "E5": e5, "E7": e7, "E8": e8, "E9": e9}
MANUAL = {"E6": "python -m bench.trace --trace trace.jsonl --system optimusdb --speed 1x",
          "E10": "needs the agent-side credential verifier merged; see README §E10",
          "E11": "python -m bench.runner E11 --gold gold.jsonl --pred pred.jsonl --extractor tinyllama"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("exp"); ap.add_argument("--config", default="config/testbed.yaml")
    ap.add_argument("--systems", nargs="*"); ap.add_argument("--reps", type=int)
    ap.add_argument("--workloads", nargs="*", choices=["WA", "WB", "WC", "WO"],
                    help="E1 only: run these workloads (WO also runs its document-size series), e.g. --workloads WO")
    ap.add_argument("--pilot", action="store_true", help="quick functional check: 1 rep, 30 s warm-up + 120 s, E1 on 5 cells; "
                    "results go to results/pilot/ and never mix with the campaign")
    ap.add_argument("--quick", action="store_true", help="every scenario once on 10^4 records in about two hours "
                    "(1 rep, short windows, reduced grids); results go to results/quick/; not for statistics")
    ap.add_argument("--yes", action="store_true"); ap.add_argument("--gold"); ap.add_argument("--pred"); ap.add_argument("--extractor")
    args = ap.parse_args()
    if args.exp == "E11":
        return e11_score(args.gold, args.pred, args.extractor)
    if args.exp not in EXPS:
        sys.exit(f"{args.exp}: {MANUAL.get(args.exp, 'unknown experiment')}")
    cfg = cfg_load(args.config)
    global RES
    if args.quick:
        RES = os.path.join(RES, "quick")
        args.reps = 1
        cfg["profile"] = "quick"
        cfg["run"] = dict(cfg["run"], warmup_s=10, duration_s=30)
        cfg["data"] = dict(cfg["data"], records=10_000)
        cfg["settle_timeout_s"] = 120
        say(f"QUICK {args.exp}: 1 rep, 10^4 records, short windows, reduced grids, results in {RES}")
    elif args.pilot:
        RES = os.path.join(RES, "pilot")
        args.reps = 1
        cfg["run"] = dict(cfg["run"], warmup_s=30, duration_s=120)
        say(f"PILOT {args.exp}: 1 rep, 30 s warm-up + 120 s measured, results in {RES}")
    record_runtime(cfg, args.exp)
    asyncio.run(EXPS[args.exp](cfg, args))


def record_runtime(cfg, exp):
    """Log the systems' runtime settings and keep them next to the results (runtime-settings.json, one entry
    per experiment start), so every result can be traced to the settings it ran with."""
    try:
        from . import cluster as C
        rt = C.runtime_summary(cfg)
    except Exception as ex:  # noqa: BLE001  (multi-host configs without limits still run)
        say(f"runtime settings not recorded: {type(ex).__name__}: {ex}"); return
    for role, env in rt.get("optimusdb", {}).items():
        say(f"OptimusDB runtime ({role}): " + " ".join(f"{k}={v}" for k, v in sorted(env.items())))
    os.makedirs(RES, exist_ok=True)
    path = os.path.join(RES, "runtime-settings.json"); hist = []
    if os.path.exists(path):
        try: hist = json.load(open(path))
        except ValueError: hist = []
    hist.append({"exp": exp, "started": time.strftime("%Y-%m-%d %H:%M:%S"), "settings": rt})
    with open(path, "w") as f: json.dump(hist, f, indent=1)


if __name__ == "__main__":
    main()
