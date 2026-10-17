"""Baseline calibration: are a system's failures its own behaviour, or a problem of the benchmark?
(run inside odb-bench; calibrate-baselines.ps1 pipes this file in.)

For each system (SYSTEMS, default gun,autobase,opendht) and workload (WORKLOADS, default WA,WO) it runs the
workload on cloud-a at rising rates (5, 10, 25, 50 ops/s, 20 s each, stopping after the first rate with > 50 %
errors) in two setups:
  single   the system on cloud-a only, no peers, unshaped network (skipped for OpenDHT: a DHT needs peers)
  cluster  the normal 8-host cluster, with the Table 7 link profiles as in E1 (CLUSTER_NETEM=0: unshaped)
Every setup starts from a fresh deployment, so one workload cannot leave a backlog for the next.
AUTOBASE_INDEXERS=<n> makes only the first n Autobase nodes indexers (default: all 8).
and records per rate: achieved ops/s, P50/P99, error rate and the commonest error, and cloud-a's CPU and memory
from the host agent. Unshaped network, RECORDS documents of 2 KB (default 10,000, as in E1).

How to read it (also printed per system):
  * fails at a low rate in the SINGLE setup while CPU stays well below its limit  -> suspect the wrapper or the
    harness (nothing is saturated, yet operations fail): must be fixed before results count;
  * CPU at its limit when it fails                                              -> the system is saturated
    under the testbed's CPU limit: its real behaviour on this hardware;
  * single setup fine, cluster setup fails                                      -> the cost of replicating with
    7 peers: its real behaviour (the paper can say so);
  * the node stops answering                                                    -> a crash: its log is saved.
Report: results/logs/calibration-<time>.txt
"""
import asyncio, collections, json, os, statistics, sys, time
sys.path.insert(0, "/bench")
import httpx
from bench import adapters as A, cluster, faults
from bench.loadgen import run_open_loop
from bench.workloads import Workload, make_doc

CFG = json.loads(open("/config/testbed.yaml").read().split("\n", 1)[1])
SYSTEMS = [s for s in os.environ.get("SYSTEMS", "gun,autobase,opendht").split(",") if s]
RATES = [float(x) for x in os.environ.get("RATES", "5,10,25,50").split(",")]
N = int(os.environ.get("RECORDS", "10000"))
DUR = int(os.environ.get("DURATION", "20"))
WORKLOADS = [w for w in os.environ.get("WORKLOADS", "WA,WO").split(",") if w]
CLUSTER_NETEM = os.environ.get("CLUSTER_NETEM", "1") != "0"
if os.environ.get("AUTOBASE_INDEXERS"): CFG["autobase_indexers"] = int(os.environ["AUTOBASE_INDEXERS"])
NO_SINGLE = {"opendht": "a DHT stores values on other nodes, so a single node cannot accept writes"}
OUT = f"/results/logs/calibration-{time.strftime('%Y%m%d-%H%M%S')}.txt"
LINES = []


def say(*a):
    line = " ".join(str(x) for x in a); LINES.append(line); print(line, flush=True)
    with open(OUT, "w") as f: f.write("\n".join(LINES) + "\n")


SINGLE_ENV = {"gun": {"PEERS": ""}, "autobase": {"BOOTSTRAP": "", "PEERS": ""}, "opendht": {"DHT_BOOTSTRAP": ""},
              "iroh": {"TICKET": ""}, "corrosion": {"BOOTSTRAP": ""}}


async def start(ag, sysid, hosts, single):
    await ag.all(hosts, "POST", "/systems/stop-all")
    await ag.all(hosts, "POST", f"/system/{sysid}/wipe")
    if single:
        env = dict(SINGLE_ENV.get(sysid, {}))
        if sysid == "optimusdb": env = cluster.optimusdb_env(CFG, hosts[0])
        if sysid == "corrosion": env.update(cluster.QUIET_ENV["corrosion"])
        await ag.call(hosts[0], "POST", f"/system/{sysid}/start", {"env": env})
        await cluster.wait_ready(sysid, [hosts[0]])
    else:
        await cluster.start_joined(ag, sysid, hosts)


async def sample(ag, h, sysid, stop, out):
    while not stop.is_set():
        try:
            s = await ag.call(h, "GET", f"/stats/odb-{h['name']}-{sysid}")
            out.append((s.get("cpu_pct"), s.get("mem_mb")))
        except Exception:  # noqa: BLE001
            pass
        try: await asyncio.wait_for(stop.wait(), 3)
        except asyncio.TimeoutError: pass


async def alive(sysid, h):
    try:
        await cluster.wait_ready(sysid, [h], timeout_s=15); return True
    except Exception:  # noqa: BLE001
        return False


NODE_JS = {"gun", "autobase"}   # one JavaScript thread: about 100 % (one core) is their ceiling whatever the limit


async def calibrate(sysid, single, wl):
    hosts = cluster.hosts_of(CFG); h0 = hosts[0]
    limit = float(h0.get("cpus") or 0) * 100 or None
    if limit and sysid in NODE_JS: limit = min(limit, 100.0)
    setup = ("single" if single else "cluster" + (" + links" if CLUSTER_NETEM else "")) + f" {wl}"
    ag = cluster.Agents(CFG); rows = []; nodes = cluster.nodes(CFG)
    try:
        faults.clear_netem(nodes)
        t = time.time(); await start(ag, sysid, hosts, single)
        ad = cluster.adapter_for(CFG, sysid, h0, local=False); await ad.open()
        try:
            await ad.load([make_doc(i, "2KB") for i in range(N)])
            say(f"  [{setup}] started and loaded {N} documents in {time.time() - t:.0f} s")
            await asyncio.sleep(5 if single else 15)
            if not single and CLUSTER_NETEM:
                faults.apply_netem(nodes, cluster.links(CFG)); await asyncio.sleep(3)
            for rate in RATES:
                stop = asyncio.Event(); st = []
                smp = asyncio.create_task(sample(ag, h0, sysid, stop, st))
                recs, dropped = await run_open_loop(ad, Workload(wl, N, "2KB", seed=int(rate)), rate, DUR, 0)
                stop.set(); await smp
                # operations the interface cannot express (OpenDHT queries) are not errors, as in the results
                uns = sum(1 for r in recs if not r.ok and r.err.startswith("NotImplementedError"))
                recs = [r for r in recs if r.ok or not r.err.startswith("NotImplementedError")]
                ok = sorted(r.latency_ms for r in recs if r.ok); errs = [r.err.split(":")[0] for r in recs if not r.ok]
                er = len(errs) / len(recs) if recs else 1.0
                q = lambda p: ok[min(len(ok) - 1, int(p * len(ok)))] if ok else float("nan")
                cpu = max((c for c, _ in st if c is not None), default=None)
                mem = max((m for _, m in st if m is not None), default=None)
                top = collections.Counter(errs).most_common(1)
                up = await alive(sysid, h0)
                rows.append(dict(rate=rate, achieved=len(ok) / DUR, p50=q(.5), p99=q(.99), err=er, top=top[0] if top else None,
                                 cpu=cpu, mem=mem, alive=up))
                say(f"  [{setup}] {rate:4.0f} ops/s: achieved {len(ok) / DUR:5.1f}  P50 {q(.5):8.1f} ms  P99 {q(.99):8.1f} ms  "
                    f"errors {100 * er:5.1f} %{(' (' + top[0][0] + ' x' + str(top[0][1]) + ')') if top else ''}  "
                    f"CPU max {cpu if cpu is not None else '?'} %{(' of ' + str(int(limit))) if limit else ''}  "
                    f"mem {mem if mem is not None else '?'} MB{(' unsupported ' + str(uns)) if uns else ''}{'' if up else '  NODE STOPPED ANSWERING'}")
                if not up:
                    try:
                        r = await ag.call(h0, "GET", f"/logs/{sysid}?tail=80")
                        say("  --- last log lines of cloud-a ---"); [say("  | " + l) for l in ((r.get("stdout") or "") + (r.get("stderr") or "")).splitlines()[-40:]]
                    except Exception:  # noqa: BLE001
                        pass
                    break
                if er > 0.5: break
                await asyncio.sleep(3)
        finally:
            await ad.close()
    except Exception as ex:  # noqa: BLE001
        say(f"  [{setup}] could not run: {type(ex).__name__}: {ex}")
    finally:
        try: faults.clear_netem(nodes)
        except Exception: pass  # noqa: BLE001
        await ag.close()
    return rows, limit


def verdict(single, multi, limit):
    def first_fail(rows):
        return next((r for r in (rows or []) if r["err"] > 0.05 or not r["alive"]), None)
    fs, fm = first_fail(single), first_fail(multi)
    hot = lambda r: r and limit and r["cpu"] is not None and r["cpu"] >= 0.85 * limit
    if single is None:   # not applicable (DHT): judge the cluster alone
        if not fm: return f"no failures up to {multi[-1]['rate']:.0f} ops/s in the cluster" if multi else "cluster did not run: no verdict"
        if not fm["alive"]: return f"CRASH in the cluster at {fm['rate']:.0f} ops/s: see the log lines"
        return (f"{'REAL (CPU-bound)' if hot(fm) else 'CHECK'}: fails at {fm['rate']:.0f} ops/s in the cluster with CPU at "
                f"{fm['cpu']}% (limit {limit:.0f}%)" if limit else f"fails at {fm['rate']:.0f} ops/s in the cluster")
    if not single:
        return "single setup did not run: no verdict"
    if fs and not fs["alive"]:
        return f"CRASH in the single setup at {fs['rate']:.0f} ops/s: see the log lines; a crash is a wrapper bug until the log shows otherwise"
    if fs and not hot(fs):
        return (f"SUSPECT BENCHMARK: fails at {fs['rate']:.0f} ops/s on a single node with CPU at {fs['cpu']}% "
                f"(limit {limit:.0f}%): nothing is saturated, so the wrapper or harness must be checked")
    if fs and hot(fs):
        return f"REAL (CPU-bound): saturates at {fs['rate']:.0f} ops/s on a single node with CPU at its limit"
    if fm and not fm["alive"]:
        return f"CRASH in the cluster at {fm['rate']:.0f} ops/s (single node fine): see the log lines"
    if fm:
        return (f"REAL (replication cost): fine on a single node up to {single[-1]['rate']:.0f} ops/s, fails at "
                f"{fm['rate']:.0f} ops/s with 7 peers{' (CPU at its limit)' if hot(fm) else ''}")
    return f"no failures up to {multi[-1]['rate'] if multi else single[-1]['rate']:.0f} ops/s in either setup"


async def main():
    say("Baseline calibration", time.strftime("%Y-%m-%d %H:%M:%S"), f"systems {','.join(SYSTEMS)}, workloads {','.join(WORKLOADS)}, "
        f"rates {RATES}, {DUR} s each, {N} records, cluster {'with' if CLUSTER_NETEM else 'without'} link profiles"
        + (f", Autobase indexers {CFG['autobase_indexers']}" if CFG.get("autobase_indexers") else ""))
    summary = []
    for s in SYSTEMS:
        for wl in WORKLOADS:
            say(f"\n=== {s} {wl}")
            if s in NO_SINGLE:
                say(f"  [single] not applicable: {NO_SINGLE[s]}"); single, limit = None, None
            else:
                single, limit = await calibrate(s, True, wl)
            multi, lim2 = await calibrate(s, False, wl)
            v = verdict(single, multi, limit or lim2); summary.append((f"{s} {wl}", v))
            say(f"  VERDICT {s} {wl}: {v}")
    say("\n=== Summary")
    for s, v in summary: say(f"  {s:12} {v}")
    ag = cluster.Agents(CFG)
    try: await ag.all(cluster.hosts_of(CFG), "POST", "/systems/stop-all")
    finally: await ag.close()
    say(f"\nreport: {os.path.basename(OUT)}")

asyncio.run(main())
