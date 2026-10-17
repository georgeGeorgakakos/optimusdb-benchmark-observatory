"""Observation helpers: resource sampling, convergence checking, election snapshots."""
import asyncio, re, time
from statistics import mean


# ------------------------------------------------------------------ resources (E4, E8)
async def sample_resources(node, pid_pattern="optimusdb", every_s=1.0, duration_s=60):
    """Sample CPU % and RSS of the DB process via /proc on the node (works over ssh/kubectl/docker).
    Returns list of (t, cpu_pct, rss_mb). CPU % is relative to one core × number of cores (0–100)."""
    out = []
    script = (f"P=$(pgrep -f {pid_pattern} | head -1); N=$(nproc); "
              "read a b c d e f g h < <(head -1 /proc/stat | cut -d' ' -f2-); "
              "T1=$((a+b+c+d+e+f+g+h)); U1=$(awk '{print $14+$15}' /proc/$P/stat); sleep 1; "
              "read a b c d e f g h < <(head -1 /proc/stat | cut -d' ' -f2-); "
              "T2=$((a+b+c+d+e+f+g+h)); U2=$(awk '{print $14+$15}' /proc/$P/stat); "
              "R=$(awk '/VmRSS/{print $2}' /proc/$P/status); echo $(( (U2-U1)*100*N/(T2-T1) )) $R")
    t_end = time.time() + duration_s
    while time.time() < t_end:
        txt = await asyncio.to_thread(node.sh, f"bash -c {shlex_quote(script)}", False)
        m = re.findall(r"(\d+)\s+(\d+)", txt or "")
        if m:
            cpu, rss_kb = map(int, m[-1]); out.append((time.time(), min(cpu / 1.0, 100.0 * 1), rss_kb / 1024))
        await asyncio.sleep(max(0, every_s - 1.0))
    return out


async def sample_container(node, container, every_s=1.0, duration_s=60):
    """Docker Desktop deployment: sample CPU % and memory of one container through the host agent
    (`GET /stats/<container>`, i.e. `docker stats`). Returns list of (t, cpu_pct, rss_mb, disk_mb, net_bytes)."""
    import json, urllib.request
    out, t_end = [], time.time() + duration_s
    def get():
        req = urllib.request.Request(f"{node.agent_url}/stats/{container}", headers={"x-token": node.token})
        with urllib.request.urlopen(req, timeout=30) as r: return json.loads(r.read())
    while time.time() < t_end:
        t0 = time.time()
        try:
            s = await asyncio.to_thread(get)
            out.append((t0, s.get("cpu_pct"), s.get("mem_mb"), s.get("disk_mb"), s.get("net_bytes")))
        except Exception:  # noqa: BLE001 - a missed sample is skipped
            pass
        await asyncio.sleep(max(0.0, every_s - (time.time() - t0)))
    return out


def shlex_quote(s):
    import shlex; return shlex.quote(s)


def summarize_resources(samples):
    cpu = [s[1] for s in samples if s[1] is not None]; rss = [s[2] for s in samples if s[2] is not None]
    return dict(cpu_pct=round(mean(cpu), 2) if cpu else None, rss_mb=round(mean(rss), 1) if rss else None)


# ------------------------------------------------------------------ convergence (E5, E6, E8)
async def wait_convergence(adapters, t_from, timeout_s=600, poll_s=0.5, progress=None):
    """Poll every replica's snapshot hash until all are equal. Returns (seconds since t_from, identical, n_docs)."""
    t_end = time.time() + timeout_s; t_said = time.time()
    while time.time() < t_end:
        if progress and time.time() - t_said > 60:
            t_said = time.time(); progress(f"  waiting for convergence: {time.time() - t_from:.0f} s since heal (limit {timeout_s:.0f} s)")
        # one poll may not outlast the limit (a slow replica used to keep this loop going far past timeout_s)
        left = max(1.0, t_end - time.time())
        res = await asyncio.gather(*(asyncio.wait_for(a.snapshot_hash(), left) for a in adapters), return_exceptions=True)
        hashes = [r[0] for r in res if not isinstance(r, BaseException)]
        if len(hashes) == len(adapters) and len(set(hashes)) == 1:
            return time.time() - t_from, True, res[0][1]
        await asyncio.sleep(poll_s)
    return timeout_s, False, None


class AckLog:
    """Records every acknowledged write so loss can be checked after convergence.

    Each write carries the writer's id ("writer") and its issue time ("writer_ts", set by the adapter). With
    last-writer-wins per key, a write that was overwritten by a concurrent write is not lost: concurrent writes on
    two sides of a partition cannot both survive. A key counts as lost when its final document is missing, or when
    an acknowledged write from the same partition side was ISSUED after the write that produced the final document
    had COMPLETED (so it should have won under any last-writer-wins order). Comparing raw version counters across writers, as an earlier version
    of this check did, counted ordinary overwrites as losses.
    """
    SKEW_S = 0.05          # allowance for clock differences between hosts sharing one machine clock

    def __init__(self, op_timeout_s=10.0, side_of=None):
        self.acked = {}            # key -> highest acknowledged version (kept for compatibility)
        self.writes = {}           # key -> list of (writer, version, issue_ts, ack_ts)
        self.op_timeout_s = op_timeout_s
        # side_of(writer) -> partition side. Writes made on different sides of a partition cannot see each other,
        # so they are concurrent whatever their wall-clock times; only a later write from the SAME side as the
        # surviving write proves that write should have been superseded.
        self.side_of = side_of

    def ack(self, key, version, writer=None, issue_ts=None, ack_ts=None):
        if version >= self.acked.get(key, -1): self.acked[key] = version
        if issue_ts is not None:
            self.writes.setdefault(key, []).append((writer, version, issue_ts, ack_ts if ack_ts is not None else issue_ts))

    def is_lost(self, key, doc):
        if doc is None: return True
        ws = self.writes.get(key)
        if not ws:      # no timing recorded: fall back to the version rule
            return int(doc.get("version", -1)) < self.acked.get(key, -1)
        fw, fv, fts = doc.get("writer"), doc.get("version"), doc.get("writer_ts")
        if fts is None: return True        # final document is not one of the run's writes
        # completion time of the write that produced the final document
        match = [w for w in ws if w[0] == fw and w[1] == fv]
        f_end = min(w[3] for w in match) if match else float(fts) + self.op_timeout_s   # unacknowledged: may have completed late
        rivals = ws
        if self.side_of is not None and fw is not None:
            rivals = [w for w in ws if w[0] is not None and self.side_of(w[0]) == self.side_of(fw)]
        if not rivals: return False
        latest_issue = max(w[2] for w in rivals)
        return latest_issue > f_end + self.SKEW_S

    async def lost(self, adapter, read_doc, concurrency=16, read_timeout_s=15.0, budget_s=300.0, progress=None):
        """Reads every acknowledged key (several at a time) and counts the lost ones. Returns
        (lost, checked, unreadable): `unreadable` keys raised or timed out and are not counted as lost; keys not
        reached within `budget_s` are not checked. The earlier one-key-at-a-time loop could run for hours when
        reads timed out (thousands of keys x the read timeout) with nothing in the log."""
        keys = list(self.acked); sem = asyncio.Semaphore(concurrency); t_end = time.time() + budget_s
        st = {"lost": 0, "checked": 0, "unreadable": 0}; last = [time.time()]

        async def one(k):
            async with sem:
                if time.time() > t_end: return
                try:
                    doc = await asyncio.wait_for(read_doc(adapter, k), read_timeout_s)
                except Exception:  # noqa: BLE001
                    st["unreadable"] += 1; return
                st["checked"] += 1
                if self.is_lost(k, doc): st["lost"] += 1
                if progress and time.time() - last[0] > 30:
                    last[0] = time.time(); progress(f"  loss check: {st['checked'] + st['unreadable']}/{len(keys)} keys read")

        await asyncio.gather(*(one(k) for k in keys))
        return st["lost"], st["checked"], st["unreadable"]


# ------------------------------------------------------------------ election (E9)
def parse_status(js):
    """Extract (self_id, role, leader, term, {peer_id: health_score}) from GET /<ctx>/agent/status."""
    a = js.get("agent", {}); e = js.get("election", {}); c = js.get("cluster", {})
    scores = {}
    def sc(h):
        try: return float(str(h.get("score", "nan")).replace("%", ""))
        except ValueError: return float("nan")
    if a: scores[a.get("peer_id")] = sc(a.get("health", {}))
    for p in c.get("peers", []) or []:
        scores[p.get("peer_id")] = sc(p.get("health", {}))
    return a.get("peer_id"), a.get("role"), e.get("current_leader"), e.get("current_term"), scores


def quality_ratio(scores_at_fault, elected, dead):
    live = {k: v for k, v in scores_at_fault.items() if k not in dead and v == v}
    if not live or elected not in live: return None
    return live[elected] / max(live.values())
