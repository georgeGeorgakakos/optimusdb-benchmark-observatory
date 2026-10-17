# OptimusDB Benchmark Observatory (dashboard)

A local web dashboard for the testbed, in the ICCS look. It reads `results\` only (mounted read-only) and
never starts or stops a test.

## Start / stop

```powershell
powershell -ExecutionPolicy Bypass -File .\dashboard.ps1          # starts it and opens http://localhost:8501
powershell -ExecutionPolicy Bypass -File .\dashboard.ps1 -Stop
```

`run-all.ps1` starts it automatically when it starts a test. `fresh-start.ps1` removes it with the other
testbed containers; start it again afterwards.

## Pages

| Page | What it shows |
|---|---|
| Live progress | running / finished / possibly stuck, run i of N, time left, experiment pipeline, P99 of each finished run, live log, testbed facts, "notify me when it finishes" |
| Run history | every run-all run on disk (current `results\` and every `results-archive\<folder>\`): started, finished, duration, status per experiment, "View results" |
| Run health | completion matrix (system x experiment), data-quality flags (not replicated in time, unsupported, dropped operations), failed runs, full log |
| Findings & hypotheses | H1-H5 checked against the data (supported / not supported / insufficient data), plain-language findings, E1 statistics (Mann-Whitney, Holm, Cliff's delta) |
| E1-E5 | one dashboard per experiment with charts, tables, "what this shows" and "how to read it" |
| Evaluation report | the paginated A4 report of the selected run (current or archived): cover, contents, summary, analyst notes, method, run integrity with automatic observations, E1–E5 with hypothesis checks, statistics (campaign), threats, raw data; every figure exports as SVG / PNG / CSV; Print saves a PDF |
| How to read this | setup, workloads, percentiles, modes, statistics, badges |

**When a run ends** every page shows a banner (finished / finished with errors / stopped before the end), the
browser tab title starts with ✓, ⚠ or ■, and, if you allowed it, a desktop notification appears while the page is
open. The banner is computed from the files, so it is there when you open the dashboard later; Dismiss hides it until
the next run.

**Older runs** are kept automatically: `fresh-start.ps1` moves `results\` to `results-archive\<date-time>\`, and
`run-all.ps1` moves a finished previous run of the same kind to `results-archive\<its start>-<kind>\` when you run its
experiments again (an interrupted run is continued; new experiments are added). `save-results.ps1` is only needed
for an extra labelled copy. The selector at the top lists them as
"Archived …", and the Run history page links to each. `fresh-start.ps1` starts the dashboard again at the end.

Click a finished run (or a bar of a single-repetition cell) to see every operation over time and the failures by cause.
The selector at the top switches between quick, pilot and campaign results. With fewer than 10 repetitions every
verdict is marked as indicative.

## How it works

`server.py` (Python standard library, plus scipy for the statistics) runs in the `odb-bench` image as container
`odb-dashboard`, port 8501 on localhost only. It shares the process table of `odb-bench`, so it knows whether the
benchmark is running; if `odb-bench` was not running when the dashboard started, it infers that from the log.

## Evaluation report

The **Evaluation report** page (menu group *Report*) builds the report from the result files of the run chosen in the
selector, so it always matches the files. When a run finishes, `run-all` also saves a self-contained copy,
`report-<run start>.html`, in that run's results folder; it opens offline, prints to PDF and moves to
`results-archive\` with the run. "Download saved copy" on the page downloads it.

What is generated and what is not:

* **Data** (figures, tables, verdicts) is computed from the files with the same code as the other pages.
* **Generated text** states facts filled in from the data by fixed rules (rankings, margins, which limits were met).
  **Automatic observations** list what the files and logs show (data not replicated in time, nodes that stopped,
  the load generator falling behind, wrong row counts, runs that hit a time limit), without causes.
* **Method text** (scope, testbed, workloads, threats, glossary) is fixed and changes only with the testbed.
* **Analyst notes**: interpretation is never generated. Write it in `report-notes.md` in the run's results folder
  (for example `results\quick\report-notes.md`; headings `##`, bullets `-`, `**bold**`). The report shows it unchanged
  in its own chapter; without the file the chapter is left out. Tick *Show where the text comes from* to see which
  part of each page is which.

Files: `dashboard/report_data.py` (data), `dashboard/static/report/` (renderer, styles, fixed chapters),
`dashboard/report_cli.py` (saved copy; run by `run-all`, log in `results\logs\report-*.log`).

## Zoom, results at a glance, paper figures

* **Zoom.** Every chart has an enlarge button (top right, appears on hover). The enlarged view has *All systems* /
  *Focus on OptimusDB*, log / linear, and a slider (or the mouse wheel over the chart) that sets the top of the
  y-axis; bars and points above it are cut at the top and labelled with their value. SVG and PNG export the
  enlarged chart. On the pages themselves OptimusDB is always drawn on top: its bars carry their value and are
  never thinner than 3 px, its lines are heavier and haloed, so it stays visible next to baselines 100× slower.
* **Results at a glance** (top of *Findings & hypotheses*, first figure of the report and of the paper export):
  a radar with one axis per measure (WO P99, tail ratio, saturation, Q1–Q3 query time, edge CPU, edge memory,
  convergence) and the measured values beside it, with the hypothesis verdicts. Each axis places the systems
  between the worst (inner ring) and the best (outer ring) value measured on it, on a log scale; a failed,
  diverged or unsupported measure sits at the centre. It is a position per measure, not a weighted score; the
  values next to it say by how much. Code: `static/summary-fig.js`.
* **Paper figures** (menu *Report*): every figure of the selected run on a white background, in Helvetica/Arial,
  Times or the screen font, sized for double column (7.16 in), single column (3.5 in) or 16 cm text width.
  Per figure: SVG (vector), PNG at 300 dpi for that width, CSV of the plotted values. *Download all (ZIP)* adds
  `captions.md`, `tables.tex` (booktabs tables for E1, E3, E4, E5 and the hypotheses) and a README with the run
  and build. *Print figures* prints one figure per page with its caption, for a vector PDF. The figures and
  numbers are those of the evaluation report.

## How to read this · About and Architecture

*How to read this* opens with the official description of the evaluation (purpose, provenance, status of the results, comparability) and the reading guide. Its sub-section *Architecture* (`#arch`, `static/arch.js`) draws the testbed interactively:

- pick the data store under test (its container and port appear in every host);
- scenarios: **Overview**, **Client load** (entry host cloud-a for E1–E3, edge-a for E4, every host for E5 writers), **Replication** (packets follow the emulated links; speed follows the configured one-way delay, not to scale), **Partition (E5)** with split 4 | 4 or 2 | 6;
- hover any host, link, tier, the bridge or bench for its parameters; click for details in the panel below; full-screen and pause buttons; motion stops when the system asks for reduced motion.

The facts drawn come from `tools/gen_local.py` (addresses, links), `fresh-start.ps1` (limits) and `harness/bench/faults.py` (netem and partitions). Change them in `arch.js` if the testbed changes.
