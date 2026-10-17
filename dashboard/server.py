"""OptimusDB benchmark dashboard (ICCS).

A small read-only web server: it reads results/ (raw CSVs, per-operation CSVs, logs) and serves a single-page
dashboard on http://localhost:8501 with live progress, per-experiment charts, plain-language explanations and
an indicative check of hypotheses H1-H5. It never writes to results/ and never starts or stops anything.

Runs inside the odb-bench image (Python 3 + numpy/scipy), started by dashboard.ps1 / dashboard.sh with
results/ mounted read-only at /results. Started with --pid container:odb-bench it can also see whether the
benchmark process is running; without it, "running" is inferred from how recently the log was written.

    python server.py [--results /results] [--port 8501]
"""
import argparse, csv, glob, json, math, os, re, statistics, sys, time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(HERE, "static")
RES = "/results"
ARCH = "/archive"       # results-archive\ (older runs moved there by fresh-start.ps1 or save-results.ps1), read-only
SYSTEMS = ["optimusdb", "corrosion", "gun", "autobase", "iroh", "opendht"]
LABEL = {"optimusdb": "OptimusDB", "corrosion": "Corrosion", "gun": "Gun.js", "autobase": "Autobase",
         "iroh": "Iroh docs", "opendht": "OpenDHT"}
MODES = {"campaign": "", "pilot": "pilot", "quick": "quick"}
EXPS = ["E1", "E2", "E3", "E4", "E5"]
STALL_MIN = 20          # a log silent for longer than this while "running" is reported as possibly stuck


# ------------------------------------------------------------------ helpers
def num(v):
    if v is None or v == "": return None
    try:
        x = float(v)
        return None if math.isnan(x) else x
    except (TypeError, ValueError):
        return v


def read_csv(path):
    if not os.path.exists(path): return []
    with open(path, newline="") as f:
        return [{k: num(v) if k not in ("run_id", "system", "workload", "doc_size", "path", "query", "notes",
                                         "partition_shape", "start_utc", "bottleneck", "strategy", "initiator_tier")
                 else v for k, v in r.items()} for r in csv.DictReader(f)]


def med(xs):
    xs = [x for x in xs if isinstance(x, (int, float))]
    return statistics.median(xs) if xs else None


def tail(path, n=40):
    try:
        with open(path, errors="replace") as f: return f.read().splitlines()[-n:]
    except OSError:
        return []


ARCH_RE = re.compile(r"a:([A-Za-z0-9_.-]+)/(campaign|pilot|quick)")


def res_dir(mode):
    """Folder of a result set: 'quick' / 'pilot' / 'campaign' (current results) or 'a:<archive folder>/<kind>'."""
    m = ARCH_RE.fullmatch(mode or "")
    if m:
        base = os.path.join(ARCH, m.group(1))
        if not os.path.isdir(base): return os.path.join(RES, "__none__")
        return os.path.join(base, MODES[m.group(2)]) if MODES[m.group(2)] else base
    return os.path.join(RES, MODES.get(mode, "")) if MODES.get(mode) else RES


def has_data(d): return any(os.path.exists(os.path.join(d, f"{e}_raw.csv")) for e in EXPS)


# ------------------------------------------------------------------ run history (current + archived)
STAMP_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_(\d{2}:\d{2}:\d{2}) ")


def _t(line):
    m = STAMP_RE.match(line or "")
    if not m: return None
    try: return time.mktime(time.strptime(m.group(1) + " " + m.group(2), "%Y-%m-%d %H:%M:%S"))
    except ValueError: return None


def parse_campaign(path):
    """One run-all.ps1 invocation, from its campaign log: what was planned, what ended (exit codes), finished or not."""
    cl = tail(path, 2000); name = os.path.basename(path)
    kind = "pilot" if "-pilot" in name else "quick" if "-quick" in name else "campaign"
    planned = []
    if cl:
        m = re.search(r" start (.*)$", cl[0])
        if m: planned = [x.replace("-pilot", "").replace("-quick", "") for x in m.group(1).split()]
    ended, cur = {}, None
    for l in cl:
        m = re.search(r" end (E\d) exit=(\d+)", l)
        if m: ended[m.group(1)] = int(m.group(2))
        m = re.search(r" begin (E\d)", l)
        if m: cur = m.group(1)
    finished = any(l.rstrip().endswith(" finished") for l in cl)
    start = _t(cl[0]) if cl else None
    end = _t(cl[-1]) if finished and cl else None
    return {"log": name, "kind": kind, "planned": planned, "ended": ended, "finished": finished,
            "current": cur if cur and cur not in ended and not finished else None,
            "failed": sorted(e for e, x in ended.items() if x), "start": start or os.path.getctime(path),
            "end": end, "last_write": os.path.getmtime(path)}


def history(running):
    """Every run-all invocation found in results/logs and results-archive/<folder>/logs, newest first."""
    out = []
    roots = [("", RES)] + [(os.path.basename(d), d) for d in sorted(glob.glob(os.path.join(ARCH, "*"))) if os.path.isdir(d)]
    newest = None
    for arch, root in roots:
        for p in glob.glob(os.path.join(root, "logs", "campaign*.log")):
            try: c = parse_campaign(p)
            except OSError: continue
            c["archive"] = arch
            c["source"] = (f"a:{arch}/" if arch else "") + c["kind"]
            c["has_data"] = has_data(res_dir(c["source"]))
            out.append(c)
            if not arch and (newest is None or c["start"] > newest["start"]): newest = c
    for c in out:
        if c["finished"]: c["status"] = "finished_errors" if c["failed"] else "finished"
        elif c is newest and running: c["status"] = "running"
        else: c["status"] = "stopped"
    out.sort(key=lambda c: c["start"], reverse=True)
    return out


def sources():
    """Result sets the selector can show: the current folders, then each archive folder that holds results."""
    src = [{"id": m, "kind": m, "archive": "", "has_data": has_data(res_dir(m))} for m in ("quick", "pilot", "campaign")]
    for d in sorted(glob.glob(os.path.join(ARCH, "*")), reverse=True):
        if not os.path.isdir(d): continue
        a = os.path.basename(d)
        for m in ("quick", "pilot", "campaign"):
            sid = f"a:{a}/{m}"
            if has_data(res_dir(sid)): src.append({"id": sid, "kind": m, "archive": a, "has_data": True})
    return src


def bench_running():
    """True/False when the benchmark process table is visible (shared PID namespace), None otherwise."""
    seen_bench_ns = False
    for p in glob.glob("/proc/[0-9]*/cmdline"):
        try:
            cmd = open(p, "rb").read().replace(b"\0", b" ").decode(errors="replace")
        except OSError:
            continue
        if "sleep infinity" in cmd: seen_bench_ns = True       # PID 1 of odb-bench
        if cmd.startswith("python -m bench"): return True
    return False if seen_bench_ns else None


# ------------------------------------------------------------------ live progress
DONE_RE = re.compile(r"done (E\d-\S+): ops=(\d+) errors=(\d+) p50=([\d.]+|None) ms p99=([\d.]+|None) ms")
POS_RE = re.compile(r"\[(\d+)/(\d+)\]\s+(.*)$")


def progress():
    logs_dir = os.path.join(RES, "logs")
    camp = sorted(glob.glob(os.path.join(logs_dir, "campaign*.log")), key=os.path.getmtime)
    exp_logs = sorted([p for p in glob.glob(os.path.join(logs_dir, "E*-*.log"))], key=os.path.getmtime)
    running = bench_running()
    out = {"now": time.time(), "running": running, "running_inferred": running is None}
    if camp:
        c = parse_campaign(camp[-1])
        c["started"] = c["start"]
        out["campaign"] = c
    if exp_logs:
        p = exp_logs[-1]; lines = tail(p, 4000); name = os.path.basename(p)
        pos = None
        for l in reversed(lines):
            m = POS_RE.search(l)
            if m: pos = {"i": int(m.group(1)), "n": int(m.group(2)), "what": m.group(3)}; break
        runs = []
        for l in lines:
            m = DONE_RE.search(l)
            if m:
                runs.append({"t": l[:8], "run_id": m.group(1), "ops": int(m.group(2)), "errors": int(m.group(3)),
                             "p50": None if m.group(4) == "None" else float(m.group(4)),
                             "p99": None if m.group(5) == "None" else float(m.group(5))})
        warnings = [l for l in lines if "WARNING" in l or "readable sample keys" in l][-8:]
        mtime = os.path.getmtime(p); idle_min = (time.time() - mtime) / 60
        if running is None:   # no process table: infer from the log
            fin = out.get("campaign", {}).get("finished", False)
            out["running"] = (not fin) and idle_min < STALL_MIN
        eta = None
        if out["running"] and pos and runs:
            started = os.path.getctime(p); per = (time.time() - started) / max(1, len(runs))
            eta = per * max(0, pos["n"] - pos["i"] + 1)
        out["experiment"] = {"log": name, "exp": name.split("-")[0], "pos": pos, "runs": runs[-200:],
                             "last_lines": lines[-30:], "warnings": warnings, "idle_min": round(idle_min, 1),
                             "stalled": bool(out["running"]) and idle_min > STALL_MIN, "eta_s": eta}
    # host and build facts from the newest fresh-start log
    fs = sorted(glob.glob(os.path.join(logs_dir, "fresh-start-*.log")), key=os.path.getmtime)
    if fs:
        facts = {}
        for l in tail(fs[-1], 3000):
            for key, pat in (("vm", r"Docker Desktop VM: (.*?);"), ("optimusdb_source", r"OptimusDB source: (.*)"),
                             ("limits", r"Limits per data store: (.*)"), ("netem", r"(tc netem .*)"),
                             ("smoke", r"(All six data stores .*)")):
                m = re.search(pat, l)
                if m: facts[key] = m.group(1).strip()
        out["host"] = facts
    fails = []
    for mode in MODES:
        for l in tail(os.path.join(res_dir(mode), "failures.log"), 30):
            fails.append({"mode": mode, "line": l})
    out["failures"] = fails[-30:]
    out["modes"] = [m for m in MODES if has_data(res_dir(m))]
    c = out.get("campaign")
    if out["running"] is None:   # no process table and no experiment log: infer from the campaign log
        out["running"] = bool(c) and not c["finished"] and (time.time() - c["last_write"]) / 60 < STALL_MIN
    if c:   # one overall state for the banner: running / finished / finished with errors / stopped before the end
        if c["finished"]: c["status"] = "finished_errors" if c["failed"] else "finished"
        elif out["running"]: c["status"] = "running"
        else: c["status"] = "stopped"
    out["history"] = history(out["running"])
    out["sources"] = sources()
    return out


# ------------------------------------------------------------------ analysis + plain-language explanations
def fmt_ms(x):
    if x is None: return "n/a"
    return f"{x:.0f} ms" if x >= 100 else f"{x:.1f} ms" if x >= 10 else f"{x:.2f} ms"


def note_flags(rows):
    """Data-quality flags taken from the notes column."""
    fl = {"settle_timeout": 0, "unsupported": 0, "dropped": 0, "node_down": 0, "client_limited": 0}
    for r in rows:
        n = r.get("notes") or ""
        if "client_limited=1" in n: fl["client_limited"] += 1
        if "settled=timeout" in n: fl["settle_timeout"] += 1
        if "unsupported" in n: fl["unsupported"] += 1
        if "node_down_after_run" in n: fl["node_down"] += 1
        m = re.search(r"dropped=(\d+)", n)
        if m and int(m.group(1)) > 0: fl["dropped"] += 1
    return fl


def mwu(a, b):
    """Two-sided Mann-Whitney U p-value and Cliff's delta (None when scipy is missing or n < 3)."""
    a = [x for x in a if isinstance(x, (int, float))]; b = [x for x in b if isinstance(x, (int, float))]
    if len(a) < 3 or len(b) < 3: return None, None
    try:
        from scipy import stats
        p = float(stats.mannwhitneyu(a, b, alternative="two-sided").pvalue)
    except Exception:  # noqa: BLE001
        p = None
    gt = sum(1 for x in a for y in b if x > y); lt = sum(1 for x in a for y in b if x < y)
    return p, (gt - lt) / (len(a) * len(b))


def holm(pvals):
    """Holm-adjusted p-values for a dict name -> p."""
    items = sorted([(p, k) for k, p in pvals.items() if p is not None])
    out, m, run = {}, len(items), 0.0
    for i, (p, k) in enumerate(items):
        run = max(run, min(1.0, (m - i) * p)); out[k] = run
    return out


def analyse_e1(rows):
    cells = {}
    for r in rows:
        if r.get("p99_ms") is None and "unsupported" in (r.get("notes") or ""):
            cells.setdefault((r["system"], r["workload"], r["doc_size"]), {"rows": [], "unsupported": True})
            continue
        c = cells.setdefault((r["system"], r["workload"], r["doc_size"]), {"rows": [], "unsupported": False})
        c["rows"].append(r)
    agg = []
    for (s, w, d), c in sorted(cells.items()):
        rs = c["rows"]; ops = sum((r.get("ops") or 0) for r in rs); err = sum((r.get("errors") or 0) for r in rs)
        agg.append({"system": s, "workload": w, "doc_size": d, "reps": len(rs), "unsupported": c["unsupported"],
                    "p50": med([r.get("p50_ms") for r in rs]), "p95": med([r.get("p95_ms") for r in rs]),
                    "p99": med([r.get("p99_ms") for r in rs]), "p999": med([r.get("p999_ms") for r in rs]),
                    "achieved": med([r.get("achieved_ops_s") for r in rs]),
                    "error_pct": (100.0 * err / ops) if ops else None,
                    "unsupported_ops": sum(int(m.group(1)) for r in rs for m in [re.search(r"\bunsupported=(\d+)", r.get("notes") or "")] if m),
                    "p99_list": [r.get("p99_ms") for r in rs]})
    text = []
    for w in ["WO", "WA", "WB", "WC"]:
        cs = [a for a in agg if a["workload"] == w and a["doc_size"] == "2KB" and a["p99"] is not None]
        if not cs: continue
        cs.sort(key=lambda a: a["p99"])
        best = cs[0]; od = next((a for a in cs if a["system"] == "optimusdb"), None)
        line = f"{w} (2 KB): lowest P99 {LABEL.get(best['system'], best['system'])} {fmt_ms(best['p99'])}"
        if od and od is not best:
            line += f"; OptimusDB {fmt_ms(od['p99'])} ({od['p99'] / best['p99']:.1f}× the best)"
        elif od:
            line += " (OptimusDB is the fastest here)"
        text.append(line + ".")
    bad = [a for a in agg if (a["error_pct"] or 0) > 1]
    for a in bad:
        text.append(f"{LABEL.get(a['system'], a['system'])} {a['workload']} {a['doc_size']}: {a['error_pct']:.1f}% of "
                    f"operations failed, so its latency describes only the operations that succeeded.")
    return {"cells": agg, "text": text}


def analyse_e2(rows):
    groups = {}
    for r in rows:
        groups.setdefault((r["system"], r.get("dataset_records")), []).append(r)
    series = []
    for (s, n), rs in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1] or 0)):
        pts = {}
        for r in rs: pts.setdefault(r.get("offered_ops_s"), []).append(r)
        def share(v):   # supported share of the offered operations (OpenDHT cannot run WO's queries)
            xs = [float(m.group(1)) for x in v if (m := re.search(r"supported_share=([\d.]+)", x.get("notes") or ""))]
            return med(xs) if xs else 1.0
        p = [{"offered": o, "achieved": med([x.get("achieved_ops_s") for x in v]), "p99": med([x.get("p99_ms") for x in v]),
              "error_rate": med([x.get("error_rate") for x in v]), "reps": len(v), "share": share(v),
              # a step where the load generator, not the system, was the limit says nothing about the system
              "client_limited": any("client_limited=1" in (x.get("notes") or "") for x in v)} for o, v in sorted(pts.items())]
        sat, lower = None, False
        for q in p:
            ok = q["achieved"] is not None and q["offered"] and q["achieved"] >= 0.9 * q["offered"] * q["share"] and (q["error_rate"] or 0) < 0.01
            if ok and not q["client_limited"]:
                sat = q["offered"]
            elif not ok:
                lower = q["client_limited"]   # failed only because the generator could not keep up: saturation is at least sat
                break
        series.append({"system": s, "records": n, "points": p, "saturation": sat, "lower_bound": lower})
    text = []
    for s in series:
        if s["saturation"] is not None:
            text.append(f"{LABEL.get(s['system'], s['system'])} at {int(s['records'] or 0):,} records keeps up with the offered load "
                        f"up to {s['saturation']:.0f} ops/s (achieved ≥ 90 % of offered, < 1 % errors)"
                        + (" — at least: the next step failed while the load generator was the limit, so it is not counted." if s.get("lower_bound") else "."))
        else:
            text.append(f"{LABEL.get(s['system'], s['system'])} at {int(s['records'] or 0):,} records did not keep up even at the lowest load tested.")
    return {"series": series, "text": text}


def analyse_e3(rows):
    groups = {}
    for r in rows: groups.setdefault((r["system"], r["path"], r["query"], r.get("dataset_records")), []).append(r)
    cells = [{"system": s, "path": p, "query": q, "records": n, "reps": len(v),
              "mean": med([x.get("mean_ms") for x in v]), "p95": med([x.get("p95_ms") for x in v]),
              "correct": (sum(1 for x in v if x.get("correct") == 1) / len(v)) if v else None,
              "unsupported": all((x.get("notes") or "").startswith("unsupported") for x in v),
              "failed": all((x.get("notes") or "").startswith("failed") or (x.get("mean_ms") is None and not (x.get("notes") or "").startswith("unsupported")) for x in v),
              "error": next(((x.get("notes") or "")[8:] for x in v if (x.get("notes") or "").startswith("failed")), ""),
              "rows_returned": med([x.get("rows_returned") for x in v]), "rows_expected": med([x.get("rows_expected") for x in v])}
             for (s, p, q, n), v in sorted(groups.items(), key=lambda kv: (kv[0][2], kv[0][0], kv[0][1]))]
    text = []
    for q in sorted({c["query"] for c in cells}):
        cs = [c for c in cells if c["query"] == q and c["mean"] is not None and (c["correct"] or 0) >= 0.5]
        if cs:
            cs.sort(key=lambda c: c["mean"]); b = cs[0]
            text.append(f"{q}: fastest correct answer from {LABEL.get(b['system'], b['system'])} ({b['path']}) in {fmt_ms(b['mean'])}.")
        wrong = [c for c in cells if c["query"] == q and c["mean"] is not None and (c["correct"] or 0) < 0.5]
        for c in wrong:
            text.append(f"{q}: {LABEL.get(c['system'], c['system'])} ({c['path']}) returned {c['rows_returned'] if c['rows_returned'] is not None else '?'} rows "
                        f"instead of {c['rows_expected'] if c['rows_expected'] is not None else '?'} - incomplete or wrong, so its time is not comparable.")
    return {"cells": cells, "text": text}


def analyse_e4(rows):
    groups = {}
    for r in rows: groups.setdefault((r["system"], r.get("offered_ops_s")), []).append(r)
    cells = [{"system": s, "offered": o, "reps": len(v), "cpu": med([x.get("cpu_pct") for x in v]),
              "rss": med([x.get("rss_mb") for x in v]), "disk": med([x.get("disk_mb_per_1k_docs") for x in v]),
              "net": med([x.get("net_kb_per_op") for x in v]),
              "started_ok": min([x.get("started_ok") or 0 for x in v]) if v else None}
             for (s, o), v in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1] or 0))]
    text = []
    if cells and all(c["cpu"] is None for c in cells):
        text.append("No CPU or memory figures were recorded in this run (the resource sampler had no data); "
                    "only whether each system started is shown.")
    for c in cells:
        if c["started_ok"] == 0: text.append(f"{LABEL.get(c['system'], c['system'])} did not start on the edge hosts at {c['offered']:.0f} ops/s.")
    return {"cells": cells, "text": text}


def analyse_e5(rows):
    groups = {}
    for r in rows:
        groups.setdefault((r["system"], r.get("contention_pct"), r.get("partition_s"), r.get("partition_shape")), []).append(r)
    cells = [{"system": s, "contention": c, "partition_s": p, "shape": sh, "reps": len(v),
              "availability": med([x.get("write_availability_pct") for x in v]),
              "lost": sum((x.get("lost_ack_writes") or 0) for x in v), "ack": sum((x.get("ack_writes") or 0) for x in v),
              "convergence": med([x.get("convergence_s") for x in v]),
              "identical": (sum(1 for x in v if x.get("replicas_identical") == 1) / len(v)) if v else None,
              "readable": med([x.get("keys_readable_pct") for x in v])}
             for (s, c, p, sh), v in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1] or 0, kv[0][2] or 0))]
    text = []
    for s in sorted({c["system"] for c in cells}):
        cs = [c for c in cells if c["system"] == s]
        lost = int(sum(c["lost"] for c in cs)); ident = all((c["identical"] or 0) == 1 for c in cs)
        conv = med([c["convergence"] for c in cs])
        text.append(f"{LABEL.get(s, s)}: {'no acknowledged write lost' if lost == 0 else f'{lost} acknowledged writes lost'}; "
                    f"replicas {'identical after healing' if ident else 'NOT identical in every run'}; "
                    f"median convergence {('%.1f s' % conv) if conv is not None else 'n/a'}.")
    return {"cells": cells, "text": text}


def verdict(state, text, detail=""):
    return {"state": state, "text": text, "detail": detail}


def hypotheses(a):
    """Indicative check of H1-H5 on the data present. 'insufficient' when the data cannot decide."""
    H = {}
    e1 = a.get("E1", {}).get("cells", [])
    wo = [c for c in e1 if c["workload"] == "WO" and c["doc_size"] == "2KB" and c["p99"] is not None]
    od = next((c for c in wo if c["system"] == "optimusdb"), None); base = [c for c in wo if c["system"] != "optimusdb"]
    if od and base:
        best = min(base, key=lambda c: c["p99"]); within = od["p99"] <= 1.25 * best["p99"]
        tr = lambda c: (c["p999"] / c["p50"]) if c["p999"] and c["p50"] else None
        mtr = med([tr(c) for c in base]); otr = tr(od)
        ok_tail = otr is not None and mtr is not None and otr <= mtr
        # The verdict follows the registered rule (best baseline by P99, whatever its error rate). A baseline that
        # failed part of the mix (for example every query) has a P99 over the operations it completed only, so the
        # detail also states that, and the comparison with the baselines that completed the whole mix (<= 1 % errors).
        # This line is information for the reader; it does not change the verdict.
        caveat = ""
        partial = lambda c: (c.get("error_pct") or 0) > 1 or (c.get("unsupported_ops") or 0) > 0
        if partial(best):
            full = [c for c in base if not partial(c)]
            what = (f"failed {best['error_pct']:.1f} % of its WO operations" if (best.get("error_pct") or 0) > 1
                    else f"could not run {best['unsupported_ops']} of its WO operations (unsupported)")
            caveat = f"; note: {LABEL[best['system']]} {what}, so its P99 covers only the operations it completed"
            if full:
                fb = min(full, key=lambda c: c["p99"])
                caveat += (f"; among baselines that completed the whole mix (<= 1 % errors, nothing unsupported) the best is {LABEL[fb['system']]} "
                           f"{fmt_ms(fb['p99'])} ({'within' if od['p99'] <= 1.25 * fb['p99'] else 'outside'} 25 %)")
            else:
                caveat += "; no baseline completed the whole mix (<= 1 % errors, nothing unsupported)"
        H["H1"] = verdict("supported" if within and ok_tail else "not_supported",
                          f"OptimusDB WO P99 {fmt_ms(od['p99'])} vs best baseline {LABEL[best['system']]} {fmt_ms(best['p99'])} "
                          f"({'within' if within else 'outside'} 25 %); tail ratio P99.9/P50 {otr:.1f} vs baseline median "
                          f"{mtr:.1f}." if otr and mtr else "Tail ratio not computable.",
                          f"{od['reps']} repetition(s)" + (f"; {a['E1']['flags']['client_limited']} E1 run(s) were client-limited (see Run health)"
                                                            if a.get("E1", {}).get("flags", {}).get("client_limited") else "") + caveat)
    else:
        H["H1"] = verdict("insufficient", "Needs E1 WO 2 KB results for OptimusDB and at least one baseline.")
    e2 = a.get("E2", {}).get("series", [])
    if e2:
        biggest = max((s["records"] or 0) for s in e2)
        # A system that did not keep up even at the lowest offered load has a saturation point below that load:
        # it counts as 0 ops/s in the baseline median instead of being left out (leaving it out would raise the
        # median to the systems that coped). Rule fixed before the campaign (TESTS.md, section 12).
        sat, below, lowb, unknown = {}, [], [], []
        for s_ in e2:
            if (s_["records"] or 0) != biggest: continue
            if s_.get("lower_bound"): lowb.append(LABEL.get(s_["system"], s_["system"]))
            if s_["saturation"] is not None: sat[s_["system"]] = s_["saturation"]
            elif s_.get("lower_bound"): unknown.append(LABEL.get(s_["system"], s_["system"]))   # first step client-limited
            elif s_.get("points"): sat[s_["system"]] = 0.0; below.append(s_["system"])
        o = sat.get("optimusdb"); b = [v for k, v in sat.items() if k != "optimusdb"]
        if o is not None and b:
            ok = o >= statistics.median(b)
            nb = [LABEL.get(x, x) for x in below if x != "optimusdb"]
            H["H2"] = verdict("supported" if ok else "not_supported",
                              f"Saturation at {int(biggest):,} records: OptimusDB {o:.0f} ops/s vs baseline median {statistics.median(b):.0f} ops/s"
                              + (f" ({', '.join(nb)} did not keep up at the lowest load and {'counts' if len(nb) == 1 else 'count'} as 0)" if nb else "") + ". "
                              + (f"Lower bounds (the next step failed while the load generator was the limit): {', '.join(lowb)}. " if lowb else "")
                              + (f"Not measurable (load generator the limit from the first step): {', '.join(unknown)}. " if unknown else "")
                              + "The growth of P99 from 10^3 to 10^6 records needs the full campaign.", "first half of H2 only")
        else:
            H["H2"] = verdict("insufficient", "Needs E2 load steps for OptimusDB and the baselines.")
    else:
        H["H2"] = verdict("insufficient", "No E2 results yet.")
    e3 = a.get("E3", {}).get("cells", [])
    if e3:
        verd, notes = [], []
        # H3 is registered at 10^5 and 10^6 records. Only when neither was measured (quick mode: 10^4) is the
        # verdict computed on what exists, and then it is labelled as indicative at that size.
        reg = sorted({c["records"] for c in e3 if c["records"] in (100_000, 1_000_000)})
        scale = "" if reg else "indicative at the measured size only; H3 is registered at 10^5 and 10^6 records"
        for q in ("Q1", "Q2", "Q3"):
            for n in (reg or sorted({c["records"] for c in e3 if c["query"] == q})):
                cs = [c for c in e3 if c["query"] == q and c["records"] == n and c["mean"] is not None and (c["correct"] or 0) >= 0.5]
                ods = [c for c in cs if c["system"] == "optimusdb"]
                if not ods: continue
                o = min(ods, key=lambda c: c["mean"])
                client = [c for c in cs if c["system"] in ("gun", "autobase", "iroh", "opendht")]
                cor = next((c for c in cs if c["system"] == "corrosion"), None)
                ok = all(o["mean"] < c["mean"] for c in client) and (cor is None or o["mean"] <= 1.25 * cor["mean"])
                verd.append(ok); notes.append(f"{q}@{int(n or 0):,}: {'yes' if ok else 'no'}")
        H["H3"] = verdict("insufficient" if not verd else "supported" if all(verd) else "not_supported",
                          "; ".join(notes) or "No comparable correct results for Q1-Q3.",
                          "OptimusDB faster than client-side evaluation and within 25 % of Corrosion" + (f" ({scale})" if scale else ""))
    else:
        H["H3"] = verdict("insufficient", "No E3 results yet.")
    e4 = [c for c in a.get("E4", {}).get("cells", []) if c["system"] == "optimusdb" and c["offered"] == 40]
    if e4 and e4[0]["cpu"] is not None:
        c = e4[0]; ok = c["cpu"] < 60 and (c["rss"] or 1e9) < 512
        H["H4"] = verdict("supported" if ok else "not_supported", f"OptimusDB at 40 ops/s: {c['cpu']:.0f}% CPU, {c['rss'] or 0:.0f} MB.",
                          "testbed edge hosts are containers, not Raspberry Pi 4 boards")
    else:
        H["H4"] = verdict("insufficient", "No CPU/memory figures for OptimusDB at 40 ops/s.")
    e5 = a.get("E5", {}).get("cells", [])
    o5 = [c for c in e5 if c["system"] == "optimusdb"]
    if o5:
        lost = int(sum(c["lost"] for c in o5)); ident = all((c["identical"] or 0) == 1 for c in o5)
        avail = min((c["availability"] or 0) for c in o5)
        oc = med([c["convergence"] for c in o5])
        bc = med([c["convergence"] for c in e5 if c["system"] in ("corrosion", "gun", "autobase", "iroh")])
        conv_ok = oc is not None and (bc is None or oc <= bc)
        ok = lost == 0 and ident and avail > 0 and conv_ok
        H["H5"] = verdict("supported" if ok else "not_supported",
                          f"Lost acknowledged writes {lost}; replicas identical {'in every run' if ident else 'NOT in every run'}; "
                          f"convergence {('%.1f s' % oc) if oc is not None else 'n/a'} vs baseline median {('%.1f s' % bc) if bc is not None else 'n/a'}.")
    else:
        H["H5"] = verdict("insufficient", "No E5 results for OptimusDB yet.")
    return H


def stats_e1(cells):
    """Per workload: OptimusDB vs each baseline on per-repetition P99 (Mann-Whitney, Holm, Cliff's delta)."""
    out = []
    for w in ("WA", "WB", "WC", "WO"):
        od = next((c for c in cells if c["system"] == "optimusdb" and c["workload"] == w and c["doc_size"] == "2KB"), None)
        if not od: continue
        ps, ds = {}, {}
        for c in cells:
            if c["system"] == "optimusdb" or c["workload"] != w or c["doc_size"] != "2KB": continue
            p, d = mwu(od["p99_list"], c["p99_list"]); ps[c["system"]] = p; ds[c["system"]] = d
        adj = holm(ps)
        for s in ps: out.append({"workload": w, "baseline": s, "p": ps[s], "p_holm": adj.get(s), "cliffs_delta": ds[s]})
    return out


def results(mode):
    d = res_dir(mode)
    raw = {e: read_csv(os.path.join(d, f"{e}_raw.csv")) for e in EXPS}
    fns = {"E1": analyse_e1, "E2": analyse_e2, "E3": analyse_e3, "E4": analyse_e4, "E5": analyse_e5}
    a, errors = {}, {}
    for e, fn in fns.items():          # one malformed file or row must not blank the whole dashboard
        try:
            a[e] = fn(raw[e])
        except Exception as ex:  # noqa: BLE001
            errors[e] = f"{type(ex).__name__}: {ex}"
            a[e] = {"cells": [], "series": [], "text": [f"Could not analyse {e}: {type(ex).__name__}: {ex}"]}
        a[e]["flags"] = note_flags(raw[e]); a[e]["n_runs"] = len(raw[e])
    reps = [c.get("reps", 0) for c in a["E1"].get("cells", [])]
    try:
        a["E1"]["stats"] = stats_e1(a["E1"].get("cells", []))
    except Exception as ex:  # noqa: BLE001
        a["E1"]["stats"] = []; errors["E1 statistics"] = f"{type(ex).__name__}: {ex}"
    for c in a["E1"].get("cells", []): c.pop("p99_list", None)
    try:
        hyp = hypotheses(a)
    except Exception as ex:  # noqa: BLE001
        hyp = {h: verdict("insufficient", f"Could not evaluate: {type(ex).__name__}: {ex}") for h in ("H1", "H2", "H3", "H4", "H5")}
    done = {s: {e: sum(1 for r in raw[e] if r.get("system") == s) for e in EXPS} for s in SYSTEMS}
    return {"mode": mode, "raw": raw, "analysis": a, "hypotheses": hyp, "completion": done, "errors": errors,
            "max_reps": max(reps) if reps else 0, "labels": LABEL}


def ops_detail(mode, run_id):
    if not re.fullmatch(r"[A-Za-z0-9_.|-]+", run_id or ""): return {"error": "bad run id"}
    p = os.path.join(res_dir(mode), "ops", f"{run_id}.csv")
    if not os.path.exists(p): return {"error": "no per-operation file for this run"}
    pts, kinds, errs = [], {}, {}
    with open(p, newline="") as f:
        for r in csv.DictReader(f):
            ok = r.get("ok") in ("1", "True", "true")
            k = r.get("kind", "?"); kinds.setdefault(k, [0, 0]); kinds[k][0 if ok else 1] += 1
            if not ok: e = (r.get("error") or "?").split(":")[0]; errs[e] = errs.get(e, 0) + 1
            try: pts.append([round(float(r["scheduled_s"]), 3), round(float(r["latency_ms"]), 3), 1 if ok else 0, k])
            except (KeyError, ValueError): pass
    step = max(1, len(pts) // 4000)
    return {"run_id": run_id, "points": pts[::step], "kinds": kinds, "errors": errs, "n": len(pts)}


# ------------------------------------------------------------------ http
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def send(self, code, body, ctype="application/json"):
        b = body if isinstance(body, bytes) else body.encode()
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        u = urlparse(self.path); q = parse_qs(u.query); g = lambda k, d="": (q.get(k) or [d])[0]
        try:
            if u.path == "/api/progress": return self.send(200, json.dumps(progress()))
            if u.path == "/api/results": return self.send(200, json.dumps(results(g("mode", "quick"))))
            if u.path == "/api/ops": return self.send(200, json.dumps(ops_detail(g("mode", "quick"), g("run"))))
            if u.path == "/api/report":
                import report_data
                return self.send(200, report_data.dumps(report_data.build(g("mode", "quick"))))
            if u.path == "/api/report-copy":   # a saved copy of the report (report-<stamp>.html in the run's folder)
                name = os.path.basename(g("name"))
                p = os.path.join(res_dir(g("mode", "quick")), name)
                if not re.fullmatch(r"report-[\w.-]+\.html", name) or not os.path.isfile(p): return self.send(404, "not found", "text/plain")
                with open(p, "rb") as fh: return self.send(200, fh.read(), "text/html; charset=utf-8")
            if u.path == "/api/log":
                name = os.path.basename(g("name")); arch = os.path.basename(g("archive"))
                root = os.path.join(ARCH, arch) if arch else RES
                return self.send(200, json.dumps({"name": name, "lines": tail(os.path.join(root, "logs", name), int(g("n", "300")))}))
            path = "index.html" if u.path in ("/", "") else u.path.lstrip("/")
            f = os.path.normpath(os.path.join(STATIC, path))
            if not f.startswith(STATIC) or not os.path.isfile(f): return self.send(404, "not found", "text/plain")
            ct = {".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css",
                  ".png": "image/png", ".svg": "image/svg+xml"}.get(os.path.splitext(f)[1], "application/octet-stream")
            with open(f, "rb") as fh: return self.send(200, fh.read(), ct)
        except Exception as e:  # noqa: BLE001 - the dashboard must keep serving
            return self.send(500, json.dumps({"error": f"{type(e).__name__}: {e}"}))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--results", default=RES); ap.add_argument("--port", type=int, default=8501)
    ap.add_argument("--archive", default=ARCH)
    a = ap.parse_args(); RES = a.results; ARCH = a.archive
    sys.modules["server"] = sys.modules["__main__"]   # report_data imports this module: share its settings
    sys.path.insert(0, HERE)
    print(f"OptimusDB dashboard on http://localhost:{a.port}  (results: {RES})", flush=True)
    ThreadingHTTPServer(("0.0.0.0", a.port), H).serve_forever()
