"""Saves a self-contained copy of the evaluation report for one result set (run by run-all when a run finishes).

    python /dashboard/report_cli.py --results /results --mode quick --stamp 20261015-231046

Writes <results>/<mode folder>/report-<stamp>.html: the report's page, styles, script and the run's data in one file,
so it opens offline, can be printed to PDF and stays as it was when later runs change the results folder.
"""
import argparse, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import server, report_data  # noqa: E402

STATIC = os.path.join(HERE, "static")


def page(data):
    rd = lambda *p: open(os.path.join(STATIC, *p), encoding="utf-8").read()
    title = f"OptimusDB evaluation report · {data['meta']['label']} · {(data['meta'].get('commit') or '')[:7]}"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>{rd('style.css')}
{rd('report', 'report.css')}
body.saved main.rpt {{ padding: 20px 24px 40px; max-width: 1100px; margin: 0 auto; }}
.saved-bar {{ display: flex; flex-wrap: wrap; gap: 8px 14px; align-items: center; margin-bottom: 14px; }}
.saved-bar h1 {{ font-size: 18px; margin: 0; flex: 1; min-width: 240px; }}
</style></head>
<body class="saved"><main class="rpt">
<div class="saved-bar"><h1>OptimusDB evaluation report</h1><span class="muted" id="pgcount"></span>
<button class="abtn" type="button" onclick="window.print()">Print / Save as PDF</button>
<button class="abtn ghost" type="button" onclick="OptimusReport.exportAll()">Export all figures (SVG)</button></div>
<div class="rpt-pages"><div id="pages"></div></div><div id="measure"></div><div class="toast" id="toast"></div>
</main>
<template id="tpl">{rd('report', 'template.html')}</template>
<script>window.REPORT_DATA = {report_data.dumps(data)};</script>
<script>{rd('summary-fig.js')}</script>
<script>{rd('report', 'report.js')}</script>
<script>
OptimusReport.setToast(document.getElementById('toast'));
const info = OptimusReport.render({{ data: window.REPORT_DATA, template: document.getElementById('tpl').innerHTML, host: document.getElementById('pages'), measure: document.getElementById('measure') }});
document.getElementById('pgcount').textContent = info.pages + ' pages · ' + info.figures + ' figures · saved ' + window.REPORT_DATA.meta.generated;
</script></body></html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="/results"); ap.add_argument("--archive", default="/results-archive")
    ap.add_argument("--mode", default="quick"); ap.add_argument("--stamp", default=time.strftime("%Y%m%d-%H%M%S"))
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    server.RES, server.ARCH = a.results, a.archive
    data = report_data.build(a.mode)
    out = a.out or os.path.join(server.res_dir(a.mode), f"report-{a.stamp}.html")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f: f.write(page(data))
    print(f"report saved: {out} ({os.path.getsize(out) // 1024} KB)")


if __name__ == "__main__":
    main()
