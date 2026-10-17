"""Publishes the dashboard as a static website (for GitHub Pages, or any web server).

    python tools/build_site.py                       # results/ and results-archive/ -> site/
    python tools/build_site.py --results R --archive A --out site --no-ops

The site is the dashboard itself (dashboard/static) plus a snapshot of every result set found: the current
quick / pilot / campaign results and every archived run. The dashboard's API answers are computed here once and
written as JSON files, so the published pages show exactly what the local dashboard shows, without a server.
Per-operation drill-downs are included for quick and pilot runs (small); campaign runs have hundreds of them,
so they are left out unless --ops-campaign is given. Nothing outside --out is written.
"""
import argparse, json, os, re, shutil, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DASH = os.path.join(ROOT, "dashboard")
sys.path.insert(0, DASH)
import server  # noqa: E402
sys.modules["server"] = server
import report_data  # noqa: E402


def key(mode):
    """file-system name of a result-set id: 'quick' or 'a:<folder>/<kind>' -> 'a_<folder>_<kind>'"""
    return re.sub(r"[^\w.-]", "_", mode)


def dump(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(obj if isinstance(obj, str) else json.dumps(obj, separators=(",", ":"), default=lambda o: None))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=os.path.join(ROOT, "results"))
    ap.add_argument("--archive", default=os.path.join(ROOT, "results-archive"))
    ap.add_argument("--out", default=os.path.join(ROOT, "site"))
    ap.add_argument("--no-ops", action="store_true", help="leave out every per-operation drill-down")
    ap.add_argument("--ops-campaign", action="store_true", help="also include drill-downs of campaign runs (large)")
    ap.add_argument("--title", default="OptimusDB Benchmark Observatory")
    a = ap.parse_args()
    server.RES, server.ARCH = os.path.abspath(a.results), os.path.abspath(a.archive)
    out = os.path.abspath(a.out)
    if os.path.exists(out):
        shutil.rmtree(out)
    shutil.copytree(os.path.join(DASH, "static"), out)
    data = os.path.join(out, "site-data")

    prog = server.progress()
    prog["running"] = False
    sources = [s for s in prog.get("sources", []) if s.get("has_data")]
    prog["sources"] = sources or prog.get("sources", [])
    built = time.strftime("%Y-%m-%d %H:%M")
    manifest = {"built": built, "title": a.title, "sets": [], "ops": not a.no_ops}
    n_ops = n_rep = 0
    for s in sources:
        mode = s["id"]; k = key(mode)
        try:
            res = server.results(mode)
        except Exception as e:  # noqa: BLE001
            print(f"  skipped {mode}: {type(e).__name__}: {e}"); continue
        dump(os.path.join(data, "results", k + ".json"), res)
        try:
            dump(os.path.join(data, "report", k + ".json"), report_data.dumps(report_data.build(mode)))
        except Exception as e:  # noqa: BLE001
            print(f"  {mode}: report not built ({type(e).__name__}: {e})")
        d = server.res_dir(mode)
        for name in sorted(os.listdir(d)) if os.path.isdir(d) else []:   # saved report copies
            if re.fullmatch(r"report-[\w.-]+\.html", name):
                os.makedirs(os.path.join(data, "reports", k), exist_ok=True)
                shutil.copy2(os.path.join(d, name), os.path.join(data, "reports", k, name)); n_rep += 1
        kind = s.get("kind") or mode
        if not a.no_ops and (kind != "campaign" or a.ops_campaign):
            for exp, rows in (res.get("raw") or {}).items():
                for r in rows:
                    rid = r.get("run_id")
                    if rid and os.path.exists(os.path.join(d, "ops", rid + ".csv")):
                        dump(os.path.join(data, "ops", k, rid + ".json"), server.ops_detail(mode, rid)); n_ops += 1
        manifest["sets"].append({"id": mode, "key": k})
        print(f"  {mode}: results, report" + (f", saved reports" if os.path.isdir(os.path.join(data, "reports", k)) else ""))
    dump(os.path.join(data, "progress.json"), prog)
    dump(os.path.join(data, "manifest.json"), manifest)

    # the dashboard's index page, switched to the snapshot
    idx = os.path.join(out, "index.html")
    html = open(idx, encoding="utf-8").read()
    flag = f'<script>window.ODB_STATIC = {json.dumps({"base": "site-data/", "built": built})};</script>\n'
    html = html.replace('<script src="summary-fig.js"></script>', flag + '<script src="summary-fig.js"></script>', 1)
    open(idx, "w", encoding="utf-8").write(html)
    open(os.path.join(out, ".nojekyll"), "w").close()       # GitHub Pages: serve files as they are
    print(f"site written to {out}: {len(manifest['sets'])} result sets, {n_rep} saved reports, {n_ops} drill-downs, built {built}")


if __name__ == "__main__":
    main()
