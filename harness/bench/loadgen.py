"""Open-loop load generator.

Requests are issued on a fixed schedule (constant rate or Poisson arrivals)
regardless of whether earlier requests have completed, and latency is measured
from each request's *scheduled* start. This avoids coordinated omission, which
closed-loop generators suffer when the system slows down (Schroeder et al.,
"Open versus closed: a cautionary tale", NSDI 2006).
"""
import asyncio, csv, random, time
from dataclasses import dataclass, field


@dataclass
class OpRecord:
    scheduled: float
    start: float
    end: float
    kind: str
    ok: bool
    err: str = ""
    rows: int = -1

    @property
    def latency_ms(self):
        return (self.end - self.scheduled) * 1000.0

    @property
    def service_ms(self):
        return (self.end - self.start) * 1000.0


async def run_open_loop(adapter, workload, rate, duration_s, warmup_s=0.0, poisson=True,
                        max_inflight=2000, seed=1, timeout_s=10.0, on_op=None):
    """Issue operations at `rate` ops/s for warmup+duration seconds.
    Returns the list of OpRecord for operations scheduled after the warm-up."""
    rng = random.Random(seed)
    loop = asyncio.get_running_loop()
    t0 = loop.time() + 0.2
    total = warmup_s + duration_s
    records, tasks = [], set()
    sem = asyncio.Semaphore(max_inflight)
    dropped = 0

    async def one(sched, op):
        nonlocal dropped
        kind, key, payload = op
        start = loop.time()
        ok, err, rows = True, "", -1
        try:
            res = await asyncio.wait_for(adapter.execute(kind, key, payload), timeout=timeout_s)
            if isinstance(res, int): rows = res
        except Exception as e:  # noqa: BLE001 - every failure is data
            ok, err = False, type(e).__name__ + ": " + str(e)[:120]
        end = loop.time()
        if sched - t0 >= warmup_s:
            rec = OpRecord(sched - t0, start - t0, end - t0, kind, ok, err, rows)
            records.append(rec)
            if on_op: on_op(rec)
        sem.release()

    t = 0.0
    while t < total:
        sched = t0 + t
        now = loop.time()
        if sched > now:
            await asyncio.sleep(sched - now)
        if sem.locked():  # system cannot keep up even with max_inflight outstanding
            dropped += 1
        else:
            await sem.acquire()
            tasks.add(asyncio.create_task(one(sched, workload.next_op())))
        t += rng.expovariate(rate) if poisson else 1.0 / rate
        if len(tasks) > 5000:
            tasks = {x for x in tasks if not x.done()}
    if tasks:
        await asyncio.wait(tasks, timeout=timeout_s + 5)
    return records, dropped


# ---------------------------------------------------------------- several worker processes
# One Python process cannot carry every workload: at 10^5 records each WO query returns ~6,250 documents (12.5 MB
# at 2 KB) and decoding them took most of the generator's core in the pilot, which delayed every other operation.
# run_open_loop_mp issues exactly the same operations at exactly the same scheduled times (same seeds), but deals
# them round-robin to `workers` processes, each with its own event loop and connections. All processes share the
# system's monotonic clock (CLOCK_MONOTONIC, also asyncio's loop clock), so the schedule is one timeline.

def _schedule(wl_args, rate, total, poisson, seed, idx, n):
    """Operation i (in schedule order) goes to worker i % n. Every worker rebuilds the whole sequence from the
    seeds, so no payload is copied between processes and the sequence equals the single-process one."""
    from .workloads import Workload
    rng, wl = random.Random(seed), Workload(*wl_args[0], **wl_args[1])
    mine, t, i = [], 0.0, 0
    while t < total:
        op = wl.next_op()
        if i % n == idx: mine.append((t, op))
        t += rng.expovariate(rate) if poisson else 1.0 / rate; i += 1
    return mine


def _worker(idx, n, adapter_cfg, wl_args, rate, total, warmup_s, poisson, seed, timeout_s, max_inflight, conn):
    from . import adapters as A
    mine = _schedule(wl_args, rate, total, poisson, seed, idx, n)

    async def main():
        ad = A.make(adapter_cfg); await ad.open()
        loop = asyncio.get_running_loop()
        conn.send(("ready", len(mine)))
        t0 = await loop.run_in_executor(None, conn.recv)
        sem, tasks, recs, dropped = asyncio.Semaphore(max_inflight), set(), [], 0

        async def one(sched, op):
            kind, key, payload = op; start = loop.time(); ok, err, rows = True, "", -1
            try:
                res = await asyncio.wait_for(ad.execute(kind, key, payload), timeout=timeout_s)
                if isinstance(res, int): rows = res
            except Exception as e:  # noqa: BLE001 - every failure is data
                ok, err = False, type(e).__name__ + ": " + str(e)[:120]
            end = loop.time()
            if sched - t0 >= warmup_s: recs.append((sched - t0, start - t0, end - t0, kind, ok, err, rows))
            sem.release()

        c0, w0 = time.process_time(), time.monotonic()
        for t, op in mine:
            sched = t0 + t; now = loop.time()
            if sched > now: await asyncio.sleep(sched - now)
            if sem.locked(): dropped += 1; continue
            await sem.acquire(); tasks.add(asyncio.create_task(one(sched, op)))
            if len(tasks) > 5000: tasks = {x for x in tasks if not x.done()}
        if tasks: await asyncio.wait(tasks, timeout=timeout_s + 5)
        cpu = 100.0 * (time.process_time() - c0) / max(1e-6, time.monotonic() - w0)
        await ad.close()
        return recs, dropped, cpu

    try:
        conn.send(("done",) + asyncio.run(main()))
    except Exception as e:  # noqa: BLE001
        conn.send(("error", f"{type(e).__name__}: {e}"))
    finally:
        conn.close()


async def run_open_loop_mp(adapter_cfg, wl_args, rate, duration_s, warmup_s=0.0, poisson=True, workers=4,
                           max_inflight=2000, seed=1, timeout_s=10.0, start_delay_s=1.0):
    """Like run_open_loop, over `workers` processes. Returns (records, dropped, info) with
    info = {workers, worker_cpu: [% of one core per worker], ops_per_worker}."""
    import multiprocessing as mp
    ctx = mp.get_context("spawn")      # a clean interpreter: no inherited event loop or open connections
    loop = asyncio.get_running_loop(); total = warmup_s + duration_s
    pipes, procs = [], []
    for i in range(workers):
        a, b = ctx.Pipe()
        p = ctx.Process(target=_worker, daemon=True,
                        args=(i, workers, adapter_cfg, wl_args, rate, total, warmup_s, poisson, seed, timeout_s,
                              max(1, max_inflight // workers), b))
        p.start(); b.close(); pipes.append(a); procs.append(p)
    try:
        ready = await asyncio.gather(*(loop.run_in_executor(None, c.recv) for c in pipes))
        bad = [r for r in ready if r[0] != "ready"]
        if bad: raise RuntimeError("load generator worker failed to start: " + str(bad[0][1]))
        t0 = time.monotonic() + start_delay_s
        for c in pipes: c.send(t0)
        res = await asyncio.gather(*(loop.run_in_executor(None, c.recv) for c in pipes))
    finally:
        for p in procs: p.join(timeout=30)
        for p in procs:
            if p.is_alive(): p.kill()
    errs = [r for r in res if r[0] != "done"]
    if errs: raise RuntimeError("load generator worker failed: " + str(errs[0][1]))
    recs = sorted((OpRecord(*x) for r in res for x in r[1]), key=lambda r: r.scheduled)
    return recs, sum(r[2] for r in res), {"workers": workers, "worker_cpu": [round(r[3], 1) for r in res],
                                          "ops_per_worker": [r[1] for r in ready]}


def write_ops_csv(path, records):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["scheduled_s", "start_s", "end_s", "latency_ms", "service_ms", "kind", "ok", "rows", "error"])
        for r in records:
            w.writerow([f"{r.scheduled:.6f}", f"{r.start:.6f}", f"{r.end:.6f}", f"{r.latency_ms:.3f}",
                        f"{r.service_ms:.3f}", r.kind, int(r.ok), r.rows, r.err])
