"""E6: replay a captured operational trace.

Trace format (JSONL, one event per line, captured from the Swarmchestrate demonstrator
by logging every OptimusDB API call at the agents):
  {"t": 12.345, "agent": 3, "op": "update", "key": "res-000000042", "doc": {...}}
  {"t": 12.900, "agent": 1, "op": "decision", "key": "res-000000042", "criteria": {...}, "expect": {"status": "Degraded"}}
'decision' = a matchmaking query that must observe the preceding update of `key`.
End-to-end decision latency = time from the update being acknowledged to the decision query
first returning the expected state (polled every 50 ms from the decision's agent).
"""
import argparse, asyncio, json, time
import numpy as np
from . import adapters as A, observe, runner


async def replay(cfg, trace_path, system, speed, rep):
    events = [json.loads(l) for l in open(trace_path)]
    # one adapter per node, so a decision issued at agent k really runs against node k
    urls = cfg["agents"] if system == "optimusdb" else cfg["replicas"][system]
    ads = [runner.system_adapter(cfg, system, base_url=u) for u in urls]
    for a in ads: await a.open()
    acked, e2e, stal, errors, writes = {}, [], [], 0, 0
    t0 = time.time()

    async def do(ev):
        nonlocal errors, writes
        await asyncio.sleep(max(0, t0 + ev["t"] / speed - time.time()))
        a = ads[ev.get("agent", 0) % len(ads)]
        if ev["op"] in ("update", "insert"):
            writes += 1
            try:
                await a.execute(ev["op"], ev["key"], ev["doc"]); acked[ev["key"]] = (time.time(), ev["doc"])
            except Exception: errors += 1
        elif ev["op"] == "decision":
            t_ack = acked.get(ev["key"], (None,))[0]
            deadline = time.time() + 30
            while time.time() < deadline:
                try:
                    res = await a.query(ev["criteria"]) if hasattr(a, "query") else None
                    docs = res if isinstance(res, list) else (res or {}).get("results", [])
                    if any(all(d.get(k) == v for k, v in ev["expect"].items()) for d in docs if d.get("_id") == ev["key"]):
                        if t_ack: e2e.append((time.time() - t_ack) * 1000)
                        break
                except Exception: pass
                await asyncio.sleep(0.05)
            else:
                stal.append(30.0)
        else:
            try: await a.execute(ev["op"], ev.get("key"), ev.get("doc") or ev.get("criteria"))
            except Exception: errors += 1

    await asyncio.gather(*(do(ev) for ev in events))
    conv, same, _ = await observe.wait_convergence(ads, time.time(), 300) if hasattr(ads[0], "snapshot_hash") else (None, None, None)
    for a in ads: await a.close()
    e = np.asarray(e2e) if e2e else np.asarray([np.nan])
    return dict(run_id=f"E6-{system}-{speed}x-{rep}", system=system, speed=f"{speed:g}x", rep=rep,
                e2e_mean_ms=round(float(np.nanmean(e)), 2), e2e_p99_ms=round(float(np.nanpercentile(e, 99)), 2),
                max_staleness_s=round(max(e2e) / 1000, 3) if e2e else "", convergence_s=round(conv, 3) if conv else "",
                write_errors=errors, writes_total=writes, notes=f"decisions_timed_out={len(stal)}")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--trace", required=True); ap.add_argument("--system", default="optimusdb")
    ap.add_argument("--speed", type=float, default=1.0); ap.add_argument("--rep", type=int, default=1); ap.add_argument("--config", default="config/testbed.yaml")
    ap.add_argument("--campaign", action="store_true", help="all systems at 4x and OptimusDB also at 1x, `--reps` replays each, fresh deployment before every replay")
    ap.add_argument("--reps", type=int, default=5); ap.add_argument("--systems", nargs="*")
    a = ap.parse_args()
    from . import spec
    cfg = runner.cfg_load(a.config)
    sink = runner.Sink("E6", next(x for x in spec.EXPERIMENTS if x["id"] == "E6")["raw"])
    if not a.campaign:
        row = asyncio.run(replay(cfg, a.trace, a.system, a.speed, a.rep)); sink.write(row); print(row); return
    systems = a.systems or [s[0] for s in spec.SYSTEMS]
    cells = [(s, 4.0) for s in systems] + ([("optimusdb", 1.0)] if "optimusdb" in systems else [])
    for (system, speed), rep in runner.interleaved(cells, a.reps, cfg.get("seed", 1)):
        if f"E6-{system}-{speed:g}x-{rep}" in sink.done: continue
        asyncio.run(runner.cfg_reset(cfg, system))
        row = asyncio.run(replay(cfg, a.trace, system, speed, rep)); sink.write(row); print(row)


if __name__ == "__main__":
    main()
