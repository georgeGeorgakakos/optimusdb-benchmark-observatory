"""OptimusDB latency diagnosis (run inside odb-bench; diagnose-optimusdb.ps1 pipes this file in).

Two phases on a fresh 8-host OptimusDB cluster, unshaped network, 2,000 x 2 KB documents:
  A  benchmark runtime settings (bench.cluster.optimusdb_env: log level WARN, GOMAXPROCS/GOMEMLIMIT from the
     container limits, GOGC=200, no internal metrics sampling)
  B  OptimusDB defaults (no runtime settings: INFO logging, Go sized by the host's CPUs)
Each phase: load time, single-request latencies on an idle node (read LOCAL_ONLY, read LOCAL_THEN_REMOTE_MERGE,
update, insert), then 15 s of WB load at 20 ops/s with the container's CPU sampled.
Phase B minus phase A is the effect of the runtime settings. If both are slow on an idle node, the request
path itself blocks (the report shows which operation).
"""
import asyncio, json, statistics, sys, time
sys.path.insert(0, "/bench")
import httpx
from bench import adapters as A, cluster
from bench.loadgen import run_open_loop
from bench.workloads import Workload, make_doc, key_of

CFG = json.loads(open("/config/testbed.yaml").read().split("\n", 1)[1])
N = 2000
OUT = []


def say(*a):
    line = " ".join(str(x) for x in a); OUT.append(line); print(line, flush=True)


async def start(env_of):
    ag = cluster.Agents(CFG); hosts = cluster.hosts_of(CFG)
    try:
        await ag.all(hosts, "POST", "/systems/stop-all")
        await ag.all(hosts, "POST", "/system/optimusdb/wipe")
        await asyncio.gather(*(ag.call(h, "POST", "/system/optimusdb/start", {"env": env_of(h)}) for h in hosts))
        await cluster.wait_ready("optimusdb", hosts)
        async with httpx.AsyncClient(timeout=30.0) as c:
            ids = {}
            for h in hosts:
                js = (await c.get(cluster.url(h, "optimusdb", "/swarmkb/agent/status"))).json()
                ids[h["ip"]] = (js.get("agent") or {}).get("peer_id")
            for h in hosts:
                for o in hosts:
                    if o is h or not ids.get(o["ip"]): continue
                    body = {"method": {"cmd": "connect", "argcnt": 1}, "args": [f"/ip4/{o['ip']}/tcp/4001/p2p/{ids[o['ip']]}"],
                            "dstype": "", "sqldml": "", "criteria": [{}], "graph_traversal": [{}]}
                    await c.post(cluster.url(h, "optimusdb", "/swarmkb/command"), json=body)
    finally:
        await ag.close()


async def cpu(ag, h):
    try:
        s = await ag.call(h, "GET", f"/stats/odb-{h['name']}-optimusdb")
        return s.get("cpu_pct", s.get("CPUPerc", s))
    except Exception as e:  # noqa: BLE001
        return f"n/a ({type(e).__name__})"


async def timed(coro, timeout=15):
    t = time.time()
    try:
        await asyncio.wait_for(coro, timeout); return round((time.time() - t) * 1000, 1), ""
    except Exception as e:  # noqa: BLE001
        return round((time.time() - t) * 1000, 1), type(e).__name__


def summ(xs):
    v = [x for x, e in xs if not e]; errs = [e for _, e in xs if e]
    if not v: return f"all {len(xs)} failed ({', '.join(sorted(set(errs)))})"
    return (f"median {statistics.median(v):.1f} ms, max {max(v):.1f} ms, {len(errs)}/{len(xs)} failed"
            + (f" ({', '.join(sorted(set(errs)))})" if errs else ""))


async def phase(name, env_of):
    hosts = cluster.hosts_of(CFG); h0 = hosts[0]
    say(f"\n=== Phase {name}  env on {h0['name']}={env_of(h0) or '{}'}")
    t = time.time(); await start(env_of); say(f"cluster up + joined in {time.time() - t:.0f} s")
    local = A.OptimusDB(cluster.url(h0, "optimusdb"), strategy="LOCAL_ONLY")
    merge = A.OptimusDB(cluster.url(h0, "optimusdb"))
    for a in (local, merge): await a.open()
    try:
        t = time.time(); await merge.load([make_doc(i, "2KB") for i in range(N)]); say(f"load {N} docs: {time.time() - t:.1f} s")
        await asyncio.sleep(5)
        reads_l = [await timed(local.execute("read", key_of(i * 97 % N), None)) for i in range(15)]
        reads_m = [await timed(merge.execute("read", key_of(i * 89 % N), None)) for i in range(15)]
        upd = [await timed(merge.execute("update", key_of(i * 31 % N), make_doc(i * 31 % N, "2KB", version=1))) for i in range(10)]
        ins = [await timed(merge.execute("insert", f"diag-{i}", dict(make_doc(N + i, "2KB"), _id=f"diag-{i}"))) for i in range(5)]
        say("idle node, one request at a time:")
        say("  read  LOCAL_ONLY              :", summ(reads_l))
        say("  read  LOCAL_THEN_REMOTE_MERGE :", summ(reads_m))
        say("  update                        :", summ(upd))
        say("  insert                        :", summ(ins))
        ag = cluster.Agents(CFG)
        try:
            say("CPU cloud-a idle:", await cpu(ag, h0))
            task = asyncio.create_task(run_open_loop(merge, Workload("WB", N, "2KB", seed=7), 20, 15, 0))
            samples = []
            for _ in range(3):
                await asyncio.sleep(4); samples.append(await cpu(ag, h0))
            recs, dropped = await task
        finally:
            await ag.close()
        ok = [r.latency_ms for r in recs if r.ok]; errs = {}
        for r in recs:
            if not r.ok: k = r.err.split(":")[0]; errs[k] = errs.get(k, 0) + 1
        p = lambda q: sorted(ok)[min(len(ok) - 1, int(q * len(ok)))] if ok else None
        say(f"load 20 ops/s WB for 15 s: {len(recs)} ops, {len(ok)} ok, errors {errs or 0}, dropped {dropped}, "
            f"p50 {p(.5) and round(p(.5), 1)} ms, p99 {p(.99) and round(p(.99), 1)} ms")
        say("CPU cloud-a during load:", samples)
    finally:
        for a in (local, merge): await a.close()


async def main():
    say("OptimusDB latency diagnosis", time.strftime("%Y-%m-%d %H:%M:%S"))
    await phase("A (benchmark runtime settings)", lambda h: cluster.optimusdb_env(CFG, h))
    await phase("B (OptimusDB defaults)", lambda h: {})
    say("\ndone (OptimusDB is left running for inspection; the next test run stops it)")

asyncio.run(main())
