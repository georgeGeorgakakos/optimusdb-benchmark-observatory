"""Where does OptimusDB's write time go? (run inside odb-bench; profile-optimusdb.ps1 pipes this file in).

Starts a fresh 8-host OptimusDB cluster with the benchmark runtime settings plus the Go profiler on cloud-a
(OPTIMUSDB_PPROF=0.0.0.0:6060, needs a build with pprof.go), loads 10,000 x 2 KB documents, then runs the
update-heavy workload WA at the benchmark rate against cloud-a while it records, on cloud-a:
  cpu.pb.gz        CPU profile over 45 s of load
  mutex.pb.gz      lock contention (who waits on which lock)
  heap.pb.gz       memory in use
  goroutine.pb.gz  goroutines (what requests are waiting on), plus goroutines.txt (readable)
and the latency of the run (summary.txt). Unshaped network, so the profile shows OptimusDB itself.
Everything goes to results/logs/profile-<time>/ ; the PowerShell script zips it.
"""
import asyncio, json, os, statistics, sys, time
sys.path.insert(0, "/bench")
import httpx
from bench import adapters as A, cluster
from bench.loadgen import run_open_loop
from bench.workloads import Workload, make_doc

CFG = json.loads(open("/config/testbed.yaml").read().split("\n", 1)[1])
N, WARM, PROFILE_S = 10_000, 15, 45
RATE = float(os.environ.get("RATE") or CFG.get("run", {}).get("rate", 50))
WORKLOAD = os.environ.get("WORKLOAD", "WA")
OUT = f"/results/logs/profile-{time.strftime('%Y%m%d-%H%M%S')}"
os.makedirs(OUT, exist_ok=True)
LINES = []


def say(*a):
    line = " ".join(str(x) for x in a); LINES.append(line); print(line, flush=True)


async def start():
    ag = cluster.Agents(CFG); hosts = cluster.hosts_of(CFG)
    try:
        await ag.all(hosts, "POST", "/systems/stop-all")
        await ag.all(hosts, "POST", "/system/optimusdb/wipe")
        def env(h):
            e = cluster.optimusdb_env(CFG, h)
            if h is hosts[0]: e["OPTIMUSDB_PPROF"] = "0.0.0.0:6060"
            return e
        say("cloud-a environment:", env(hosts[0]))
        await asyncio.gather(*(ag.call(h, "POST", "/system/optimusdb/start", {"env": env(h)}) for h in hosts))
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
    return hosts


async def fetch(c, base, path, name, timeout=120):
    try:
        r = await c.get(base + path, timeout=timeout)
        r.raise_for_status()
        with open(os.path.join(OUT, name), "wb") as f: f.write(r.content)
        say(f"  saved {name} ({len(r.content) // 1024} KB)")
    except Exception as ex:  # noqa: BLE001
        say(f"  {name}: not collected ({type(ex).__name__}: {ex})")


async def main():
    say("OptimusDB write-path profile", time.strftime("%Y-%m-%d %H:%M:%S"), f"workload {WORKLOAD} at {RATE:.0f} ops/s")
    t = time.time(); hosts = await start(); say(f"cluster up + joined in {time.time() - t:.0f} s")
    h0 = hosts[0]; pp = f"http://{h0['ip']}:6060"
    async with httpx.AsyncClient() as c:
        try:
            (await c.get(pp + "/debug/pprof/", timeout=10)).raise_for_status()
        except Exception as ex:  # noqa: BLE001
            say(f"PROFILER NOT REACHABLE on {h0['name']}:6060 ({type(ex).__name__}). The OptimusDB build does not contain "
                "pprof.go: it must be in the repository root AND the Dockerfile must build the whole package "
                "('go build ... -o optimusdb .', not '... main.go'); push both and run fresh-start.ps1."); return
    ad = A.OptimusDB(cluster.url(h0, "optimusdb"), strategy=CFG["systems"]["optimusdb"].get("strategy", "LOCAL_THEN_REMOTE_MERGE"))
    await ad.open()
    try:
        t = time.time(); await ad.load([make_doc(i, "2KB") for i in range(N)]); say(f"load {N} docs: {time.time() - t:.1f} s")
        await asyncio.sleep(10)
        dur = WARM + PROFILE_S + 10
        say(f"running {WORKLOAD} for {dur} s; profiling cloud-a from second {WARM}")
        task = asyncio.create_task(run_open_loop(ad, Workload(WORKLOAD, N, "2KB", seed=11), RATE, dur, 0))
        await asyncio.sleep(WARM)
        async with httpx.AsyncClient() as c:
            cpu = asyncio.create_task(fetch(c, pp, f"/debug/pprof/profile?seconds={PROFILE_S}", "cpu.pb.gz", PROFILE_S + 60))
            await asyncio.sleep(PROFILE_S / 2)
            await fetch(c, pp, "/debug/pprof/goroutine", "goroutine.pb.gz")
            await fetch(c, pp, "/debug/pprof/goroutine?debug=1", "goroutines.txt")
            await cpu
            await fetch(c, pp, "/debug/pprof/mutex", "mutex.pb.gz")
            await fetch(c, pp, "/debug/pprof/heap", "heap.pb.gz")
        recs, dropped = await task
    finally:
        await ad.close()
    by = {}
    for r in recs: by.setdefault(r.kind, []).append(r)
    for kind, rs in sorted(by.items()):
        ok = sorted(r.latency_ms for r in rs if r.ok); err = len(rs) - len(ok)
        q = lambda p: ok[min(len(ok) - 1, int(p * len(ok)))] if ok else float("nan")
        say(f"{kind:7} n={len(rs):5} errors={err:4} p50={q(.5):8.1f} ms  p99={q(.99):8.1f} ms  max={(ok[-1] if ok else float('nan')):8.1f} ms")
    say(f"dropped (not issued in time): {dropped}")
    with open(os.path.join(OUT, "summary.txt"), "w") as f: f.write("\n".join(LINES) + "\n")
    say(f"PROFILE_DIR {os.path.basename(OUT)}")

asyncio.run(main())
