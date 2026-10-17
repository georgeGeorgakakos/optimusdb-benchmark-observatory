"""Data for the evaluation report of one result set (quick / pilot / campaign, current or archived).

Everything the report shows comes from here: the dashboard's own analysis and verdicts (server.results), plus what
the report needs beyond the dashboard pages (per-operation breakdowns, load-generator delay, timelines of failed
steps, build and runtime facts from the logs, automatic observations, and the run's analyst notes file).
Used by the dashboard (/api/report) and by report_cli.py, which saves a self-contained copy when a run finishes.
"""
import csv, glob, json, os, re, statistics, time


def _n0(v):
    """whole number, or – when the value is missing (older result files)"""
    try:
        return f"{float(v):.0f}"
    except (TypeError, ValueError):
        return "–"

import server

SYS = ["optimusdb", "corrosion", "gun", "autobase", "iroh", "opendht"]
NOTES_FILE = "report-notes.md"


def _q(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(p * len(xs)))] if xs else None


def _med(xs):
    xs = [x for x in xs if isinstance(x, (int, float))]
    return statistics.median(xs) if xs else None


def _ops(d, run_id):
    p = os.path.join(d, "ops", f"{run_id}.csv")
    if not os.path.exists(p): return []
    with open(p, newline="") as f: return list(csv.DictReader(f))


def _lag(rs):
    l = sorted((float(r["start_s"]) - float(r["scheduled_s"])) * 1000.0 for r in rs if r.get("start_s") and r.get("scheduled_s"))
    return {"p50": _q(l, .5), "p99": _q(l, .99), "max": l[-1] if l else None} if l else None


def _logs_dir(mode):
    m = server.ARCH_RE.fullmatch(mode or "")
    return os.path.join(server.ARCH, m.group(1), "logs") if m else os.path.join(server.RES, "logs")


def _kind(mode): return server.ARCH_RE.fullmatch(mode).group(2) if server.ARCH_RE.fullmatch(mode or "") else mode


def _exp_log(logs, kind, e):
    tag = {"quick": "-quick-", "pilot": "-pilot-"}.get(kind)
    ps = [p for p in glob.glob(os.path.join(logs, f"{e}-*.log"))
          if (tag in os.path.basename(p) if tag else re.fullmatch(rf"{e}-\d{{8}}-\d{{6}}\.log", os.path.basename(p)))]
    return max(ps, key=os.path.getmtime) if ps else None


def build(mode):
    kind = _kind(mode); d = server.res_dir(mode); logs = _logs_dir(mode)
    R = server.results(mode); raw = R["raw"]; A = R["analysis"]
    out = {"mode": mode, "kind": kind, "hypotheses": R["hypotheses"], "completion": R["completion"],
           "flags": {e: A[e]["flags"] for e in server.EXPS}, "max_reps": R["max_reps"], "errors": R["errors"]}

    # ---- meta: run, build, settings
    camp = [p for p in glob.glob(os.path.join(logs, "campaign*.log"))]
    camp = [p for p in camp if server.parse_campaign(p)["kind"] == kind]
    c = server.parse_campaign(max(camp, key=lambda p: server.parse_campaign(p)["start"])) if camp else None
    fs = sorted(glob.glob(os.path.join(logs, "fresh-start-*.log")), key=os.path.getmtime)
    ftxt = open(fs[-1], errors="replace").read() if fs else ""
    def grab(pat):
        m = re.search(pat, ftxt); return m.group(1).strip() if m else ""
    settings = None
    rs = os.path.join(d, "runtime-settings.json")
    if os.path.exists(rs):
        try: settings = json.load(open(rs))[-1].get("settings")
        except Exception: settings = None   # noqa: BLE001
    arch = server.ARCH_RE.fullmatch(mode or "")
    commit = grab(r"OptimusDB source: (\w+)")
    out["meta"] = {
        "label": ("Archived " if arch else "") + {"quick": "quick run", "pilot": "pilot", "campaign": "campaign"}.get(kind, kind),
        "archive": arch.group(1) if arch else "", "folder": d.replace(server.RES, "results").replace(server.ARCH, "results-archive"),
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"), "commit": commit, "commit_msg": grab(r"OptimusDB source: \w+ (.*)"),
        "vm": grab(r"Docker Desktop VM: (.*?);"), "limits": grab(r"Limits per data store: (.*)"), "settings": settings,
        "campaign": c, "campaign_lines": open(os.path.join(logs, c["log"])).read().splitlines() if c else [],
        "records": {e: sorted({int(r.get("dataset_records") or 0) for r in raw[e] if r.get("dataset_records")}) for e in ("E2", "E3")},
        "saved": sorted(os.path.basename(p) for p in glob.glob(os.path.join(d, "report-*.html"))),
        "files": {"results": sum(1 for e in server.EXPS if raw[e]), "ops": len(glob.glob(os.path.join(d, "ops", "*.csv"))),
                  "logs": len(glob.glob(os.path.join(logs, "*.log")))},
    }

    # ---- E1
    out["E1"] = A["E1"]["cells"]; out["E1_raw"] = raw["E1"]; out["E1_stats"] = A["E1"].get("stats", [])
    kinds, quant, lag1 = {}, {}, {}
    pcts = [0.5, 0.75, 0.9, 0.95, 0.98, 0.99, 0.995, 0.999]
    for s in SYS:
        rows = [r for r in raw["E1"] if r["system"] == s and r["workload"] == "WO" and r["doc_size"] == "2KB"]
        ops = [o for r in rows for o in _ops(d, r["run_id"])]
        if not ops: continue
        by = {}
        for o in ops:
            k = by.setdefault(o["kind"], {"ok": [], "err": 0})
            if o["ok"] in ("1", "True", "true"): k["ok"].append(float(o["latency_ms"]))
            else: k["err"] += 1
        kinds[s] = {k: {"n": len(v["ok"]), "err": v["err"], "p50": _q(v["ok"], .5), "p95": _q(v["ok"], .95), "p99": _q(v["ok"], .99)} for k, v in by.items()}
        ok = [float(o["latency_ms"]) for o in ops if o["ok"] in ("1", "True", "true")]
        quant[s] = {"p": pcts, "v": [_q(ok, p) for p in pcts]}
        lags = [_lag(_ops(d, r["run_id"])) for r in raw["E1"] if r["system"] == s]
        lag1[s] = _med([x["p50"] for x in lags if x])
    out["E1_kinds"], out["E1_wo_quantiles"], out["E1_lag"] = kinds, quant, lag1

    # ---- E2
    out["E2"] = raw["E2"]; out["E2_series"] = A["E2"]["series"]
    out["E2_lag"] = {r["run_id"]: _lag(_ops(d, r["run_id"])) for r in raw["E2"]}
    tl = {}
    for r in raw["E2"]:
        if r["system"] not in ("optimusdb", "corrosion") or (r.get("error_rate") or 0) <= 0.01: continue
        b = {}
        for o in _ops(d, r["run_id"]):
            t = int(float(o["scheduled_s"]) // 2) * 2; e = b.setdefault(t, {"ok": 0, "err": 0, "lag": []})
            e["ok" if o["ok"] in ("1", "True", "true") else "err"] += 1
            e["lag"].append((float(o["start_s"]) - float(o["scheduled_s"])) * 1000)
        tl[r["run_id"]] = [{"t": t, "ok": v["ok"], "err": v["err"], "lag50": _q(v["lag"], .5)} for t, v in sorted(b.items())]
    out["E2_timelines"] = tl

    # ---- E3, E4, E5
    out["E3"] = A["E3"]["cells"]; out["E3_raw"] = raw["E3"]
    out["E4"] = A["E4"]["cells"]; out["E4_raw"] = raw["E4"]
    out["E5"] = A["E5"]["cells"]; out["E5_raw"] = raw["E5"]
    e5log = _exp_log(logs, kind, "E5"); states = []
    if e5log:
        pend = None
        for l in open(e5log, errors="replace"):
            if "replicas not identical:" in l: pend = l.split("replicas not identical:", 1)[1].strip()
            m = re.search(r" done E5-(\w+)-(\S+?):", l)
            if m and pend: states.append({"system": m.group(1), "run": "E5-" + m.group(1) + "-" + m.group(2), "states": pend}); pend = None
    out["E5_states"] = states

    # ---- automatic observations (facts only; causes belong in the analyst notes)
    obs = []
    def add(level, exp, text): obs.append({"level": level, "exp": exp, "text": text})
    if c and not c["finished"]: add("warn", "", "The run did not reach its end (stopped or interrupted); finished experiments are reported.")
    if c and c.get("failed"): add("bad", "", "Experiments that exited with an error: " + ", ".join(c["failed"]) + ".")
    for e in server.EXPS:
        for r in raw[e]:
            n = r.get("notes") or ""
            if "settled=timeout" in n: add("warn", e, f"{server.LABEL.get(r['system'], r['system'])}: preload not readable on every host before measuring ({r['run_id']}).")
            if "node_down_after_run" in n: add("bad", e, f"{server.LABEL.get(r['system'], r['system'])}: a node stopped answering during {r['run_id']}.")
            if "client_limited=1" in n: add("warn", e, f"{r['run_id']}: the load generator was the limit (marked client-limited).")
    for rid, lg in out["E2_lag"].items():
        if lg and lg["p50"] is not None and lg["p50"] > server_lag_limit():
            add("warn", "E2", f"{rid}: operations issued a median {_n0(lg['p50'])} ms late (load generator behind schedule).")
    for cc in out["E3"]:
        if cc["mean"] is not None and (cc["correct"] or 0) < 0.5:
            add("bad", "E3", f"{server.LABEL.get(cc['system'], cc['system'])} ({cc['path']}) {cc['query']} at {int(cc['records'] or 0):,} records: {_n0(cc['rows_returned'])} rows instead of {_n0(cc['rows_expected'])}.")
    for cc in out["E5"]:
        if cc["convergence"] is not None and (cc["identical"] or 0) < 1:
            add("warn", "E5", f"{server.LABEL.get(cc['system'], cc['system'])}: replicas not identical within the convergence limit (contention {_n0(cc['contention'])} %, partition {_n0(cc['partition_s'])} s).")
    for e in ("E1", "E3", "E5"):
        p = _exp_log(logs, kind, e)
        if not p: continue
        for l in open(p, errors="replace"):
            m = re.search(r"WARNING: replicas of (\w+) not identical after the preload", l)
            if m: add("warn", e, f"{server.LABEL.get(m.group(1), m.group(1))}: replicas not identical after the preload; measured anyway.")
    seen = set(); out["observations"] = [o for o in obs if not (o["text"] in seen or seen.add(o["text"]))]

    # ---- analyst notes (written by a person after review; shown unchanged)
    np_ = os.path.join(d, NOTES_FILE)
    out["notes"] = open(np_, errors="replace").read() if os.path.exists(np_) else None
    out["notes_path"] = (out["meta"]["folder"] + "\\" + NOTES_FILE).replace("/", "\\")
    return out


def server_lag_limit(): return 10.0     # ms; same as CLIENT_LAG_P50_MS in bench/runner.py


def dumps(data):
    return json.dumps(data, separators=(",", ":"), default=lambda o: None).replace("</", "<\\/")
