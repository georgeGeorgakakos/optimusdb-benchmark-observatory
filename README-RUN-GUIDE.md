# Run guide: from a clean testbed to results for Section 8

This guide is the exact sequence for running the evaluation on one Windows PC with Docker Desktop. It
assumes the testbed was set up once (README-WINDOWS.md, parts A–C) and that the fresh start passed.
What each test does, with every parameter, is in [TESTS.md](TESTS.md).

**Where to type the commands.** Open **Windows PowerShell** and go to the package folder:

```
cd C:\odb\optimusdb-deploy
```

Every script is started as `powershell -ExecutionPolicy Bypass -File .\<script>.ps1`, which avoids the
security prompts. With PowerShell 7 installed, `pwsh` works in place of `powershell`.

---

## Overview

| Step | What | Command | Time | You |
|---|---|---|---|---|
| 1 | Update the package | unzip over the folder | 1 min | yes |
| 2 | Fresh start | `fresh-start.ps1` | 10–25 min | start it |
| 3 | Pilot | `run-all.ps1 -Pilot` | 2–3 h | start it |
| 4 | Review the pilot | commands below | 10 min | **decide** |
| 5 | Campaign E1–E5 | `run-all.ps1` | ~7–10 days | start it, check daily |
| 6 | E6 (when the trace exists) | `run-all.ps1 -Exps E6` | depends on the trace | start it |
| 7 | Results and statistics | `bench.analyze` commands | 30 min | yes |
| 8 | Archive | copy three folders | 10 min | yes |

Steps 3, 5 and 6 run unattended inside Docker. You can close the PowerShell window; only the PC and
Docker Desktop must stay on.

---

## Rules that keep the results valid

1. **Only one test at a time.** `run-all` refuses to start while another test runs. Don't run other heavy
   programs on the PC during the campaign; they compete for the same CPU.
2. **Don't change the testbed in the middle of a test.** That includes limits, `versions.env` and the
   package files. If you must, stop the test, run a fresh start, and restart that test from the beginning
   (move its `results\<E>_raw.csv` away first).
3. **Keep the PC awake.** Sleep must be set to *Never* (README-WINDOWS.md, part A6). Windows Update can
   restart the PC: pause updates for the duration of the campaign.
4. **Pilot results are never mixed with campaign results.** They live in `results\pilot\`.
5. **Never edit the CSV files by hand.** Copy them for the workbook instead.

---

## Step 0 — Which OptimusDB code is built

The testbed builds OptimusDB exactly as it is in your repository; it changes nothing in the code.
`versions.env` sets the source:

```
OPTIMUSDB_SRC=https://github.com/georgeGeorgakakos/optimusdb.git#479504d17e1d85ffbba6ee31ef173a9a98ac119c
```

The package now pins commit `479504d` (the build of quick run 6 and the pilot). To test newer code, push it
and put its hash here (or `#main` while you are still changing the code).

* `#main` builds the latest commit pushed to `main`. Use it while you are still changing the code.
* For the paper's final campaign, replace `main` with the full commit hash (`git rev-parse HEAD` after the push),
  so every run uses the same code, and cite that hash in Section 8.

During fresh start the build prints the commit it uses and checks that the batched ingestion code is present:

```
  [OK]   OptimusDB source: <hash> <commit message>
  [OK]   Batched ingestion code found (app\batch_put.go, third_party\go-orbit-db)
```

A `[WARN] This commit does NOT contain the batched ingestion code` line means the changes are not pushed yet.
The next line must be `[OK] Performance code found (group commit, field indexes, document cache)`; a `[WARN]`
there means the latest OptimusDB changes are not on `main` yet.

The testbed starts OptimusDB with its benchmark runtime settings: log level WARN, `GOMAXPROCS` and
`GOMEMLIMIT` from each container's CPU and memory limits, `GOGC=200`, internal metrics sampling off.
`check-optimusdb.ps1` prints them for cloud-a and edge-a, and each run saves them in
`results\<mode>\runtime-settings.json`. To change one, create `testbed-overrides.json` next to `run-all.ps1`
and run `fresh-start.ps1` again (the generated `testbed.yaml` is rewritten on every deploy). Example:

```
{"optimusdb_runtime": {"log_level": "INFO", "env": {"SERVICE_CONCURRENCY": 1, "OPTIMUSDB_GROUP_COMMIT": "false"}}}
```

`null` removes a setting (for example `"go_limits": false` or `"log_level": null`).

---

## Step 1 — Update the package

Unzip the newest `optimusdb-deploy.zip` over `C:\odb\optimusdb-deploy` and replace all files. Your
`results`, `results-archive` and `trace` folders are not in the zip and stay untouched.

---

## Step 2 — Fresh start

```
powershell -ExecutionPolicy Bypass -File .\fresh-start.ps1
```

* It stops any running test, removes all testbed containers and data volumes, moves old results to
  `results-archive\<timestamp>\`, rebuilds what changed, starts the testbed and smoke-tests all six systems.
* If Windows still shows a "Security warning", answer **R** (run once). The script unblocks all files.
* Add `-SkipSmoke` to save ~15 minutes, but only if all six systems passed a smoke test since the last
  package update.

**Expected end:**

```
==> Smoke test summary
  System     Result Visible on last host (s)
  optimusdb  PASS   ...
  ...
  [OK]   All six data stores form a cluster and replicate
Fresh testbed ready. Next:  .\run-all.ps1 -Pilot   then   .\progress.ps1 -Watch
```

If any row says FAIL, stop here and send `results\logs\fresh-start-<timestamp>.log`.
Details: [README-FRESH-START.md](README-FRESH-START.md).

---

## Optional — Quick run of all scenarios (about 1.5–2 hours)

```
powershell -ExecutionPolicy Bypass -File .\run-all.ps1 -Quick
powershell -ExecutionPolicy Bypass -File .\progress.ps1 -Watch
```

Runs E1 → E2 → E3 → E4 → E5 once each on 10⁴ records with short windows and reduced grids (TESTS.md,
section 8). Results go to `results\quick\`. Use it for a first look at every scenario; it has one repetition,
so its numbers carry no confidence intervals or significance tests and are not the campaign.

## Step 3 — Pilot (2–3 hours)

```
powershell -ExecutionPolicy Bypass -File .\run-all.ps1 -Pilot
```

* **Expected output:** `Applying the Table 7 link profiles`, `"netem applied"`, `[OK] Started pilot: E1`,
  and the command returns.
* **What runs:** E1 with 1 repetition, 30 s warm-up and 120 s measured, on 5 cells per system
  (WA, WB, WC, WO at 2 KB; WO at 8 KB). That is 30 runs of 2.5 minutes, in 12 blocks: each system loads
  its 2 KB dataset once for its four 2 KB runs, and its 8 KB dataset once for the 8 KB run.

**Watch it:**

```
powershell -ExecutionPolicy Bypass -File .\progress.ps1 -Watch
```

```
Pilot (campaign-pilot-20261012-210000.log): running E1

E1 (pilot)  RUNNING   log: results\logs\E1-pilot-20261012-210000.log
  run 7 of 30 (20 %): iroh WO 8KB rep 1
  now: 21:31:05   measuring: 30 s warm-up + 120 s at 50 ops/s
  about 4.9 min per run; time left about 1h 58m (finish around Mon 23:29)
  finished runs in results\pilot\E1_raw.csv: 6
    autobase   1
    ...
  failed runs (E1): 0
```

The times above are an illustration. Times in the logs are **UTC** (the containers' clock), 3 hours behind
Athens time in summer. Each run first loads its data and waits until it is on every host
(`replicated on every host after … s`); only then does `measuring` start. Ctrl+C stops watching; the pilot keeps running. When it has finished,
the first line reads `Pilot (...): finished` and every data store is stopped.

**Check the network emulation** while the pilot runs (in a second window):

```
docker exec odb-cloud-a-net ping -c 5 10.88.0.15
```

Expect about **140 ms** per ping (70 ms one-way to edge-a, each direction). Under 1 ms means the delays are
not applied: stop and report it.

---

## Step 4 — Review the pilot (you decide)

Run these four commands and send the output:

```
Import-Csv results\pilot\E1_raw.csv | Format-Table system, workload, doc_size, ops, errors, p50_ms, p99_ms, notes
Import-Csv results\pilot\E1_raw.csv | Group-Object system | Select-Object Name, Count
Get-Content results\pilot\failures.log
docker stats --no-stream
```

The last one only shows something while a system is running; skip it after the pilot has finished.

**Checklist** (the campaign should not start until each line is true or understood):

| Check | Expected | If not |
|---|---|---|
| Rows | 30 in total, 5 per system | runs failed: see `failures.log` |
| `failures.log` | missing or empty | send its content |
| `ops` | about 6,000 per run (50 ops/s × 120 s) | far fewer: the load generator was blocked (look at `dropped=` in `notes`) |
| `settled=` in `notes` | a number of seconds for every system | `settled=timeout`: the data did not reach every host; send the `readable sample keys per host` line from the log |
| `notes` | `dropped=0` | the system could not keep up; tell me which |
| `errors` for WA, WB, WC | below 1 % of `ops` | look at that system's log (README-WINDOWS.md, part D) |
| `errors` for WO | OpenDHT about 10 % (its queries are unsupported); Gun.js, Autobase and Iroh docs may show query timeouts; OptimusDB and Corrosion below 1 % | send the rows |
| `p50_ms` / `p99_ms` | present for every system | empty means no successful operation: send the rows |
| CPU during the pilot | not pinned at 100 % (Task Manager → *VmmemWSL*) | lower the limits with a fresh start (`-CpusEdge` etc.) and repeat the pilot |

**After the first pilot (17 Oct 2026) — re-check with the fixed harness before the campaign:**

1. Load generator, WO cells only (about 40 minutes):
   ```
   powershell -ExecutionPolicy Bypass -File .\run-all.ps1 -Pilot -Workloads WO -Systems optimusdb,corrosion
   ```
   Pass: in `notes`, `workers=4`, `client_cpu` below 85 and no `client_limited=1` for the 2 KB and 8 KB runs.
2. Full E1 pilot again (all systems; 2–3 hours): `.\run-all.ps1 -Pilot`. Expected now: no `PoolTimeout` in
   `failures.log`; Gun.js nodes no longer run out of memory; Autobase, Gun.js and Iroh WO queries may still
   time out (their own scan cost, see TESTS.md); Autobase edge nodes may still stop at 10⁵ (memory near 2 GB).
3. Pilot of the other scenarios at campaign sizes (several hours, mainly the 10⁶ cells):
   ```
   powershell -ExecutionPolicy Bypass -File .\run-all.ps1 -Pilot -Exps E2,E3,E4,E5
   ```
4. Decide the H1 comparison (TESTS.md, "H1 comparison detail") and write the decision into TESTS.md.

**Before step 5, also settle:**
1. **One-way or round-trip delays** (TESTS.md, section 11.2). The testbed applies the Table 7 values per direction.
2. **10⁶-record cells in E2 and E3** (TESTS.md, section 11.1). These will probably fail for OpenDHT for lack of
   memory. Decide whether that is a result or whether the limits change.

Nothing continues by itself: the campaign starts only when you run step 5.

---

## Step 5 — The campaign (E1 → E5, about 7–10 days)

```
powershell -ExecutionPolicy Bypass -File .\run-all.ps1
```

* It applies the link profiles, then runs E1, E2, E3, E4 and E5 one after another inside Docker.
* E6 is skipped automatically while `trace\trace.jsonl` does not exist (a yellow WARN line says so).
* Each test uses the campaign settings in TESTS.md: 10 or 5 repetitions, full windows.

**Daily check (2 minutes):**

```
powershell -ExecutionPolicy Bypass -File .\progress.ps1
```

* The `Campaign (...)` line shows which tests are done, running and waiting.
* `run i of N` and `time left` are shown for E1 and E5. E2, E3 and E4 show their last step instead.
* `failed runs` should stay at 0 or close to it. A handful is normal (they are retried when the test is
  started again); a steady stream is not: send the last lines.

**Approximate order and length:**

| Test | Duration | What you will see in the log |
|---|---|---|
| E1 | ~2 days | `== block b/24: <system> <size>`, `reset`, `loading`, `replicated…`, then per run `[i/420] <system> <workload> <size> rep r`, `measuring`, `done` |
| E2 | 1.5–2.5 days | `[b/24] E2 block <system> <records>`, `loading`, then one `measuring` and `done` line per load step |
| E3 | 0.5–1.5 days | `[b/21] E3 block <system> <path> <records>`, `loading`, then `done E3 … rep r` per repetition |
| E4 | ~12 h | `[b/6] E4 block <system>`, `loading 10000 records`, then `E4 <system> rep r: <rate> ops/s for 300 s` |
| E5 | 1.5–2.5 days | `== block b/6: <system>`, then per run `[i/600] <system> <contention> <partition s> <shape> rep r` and `done …: availability= lost= convergence_s=` |

---

## Step 6 — E6 (once the trace exists)

1. Save the captured trace as `C:\odb\optimusdb-deploy\trace\trace.jsonl`. The format is in TESTS.md, section 7.
2. After the campaign has finished:
   ```
   powershell -ExecutionPolicy Bypass -File .\run-all.ps1 -Exps E6
   ```

---


## Dashboard

A web dashboard shows live progress, charts per experiment, plain-language findings and the hypotheses check:

```powershell
powershell -ExecutionPolicy Bypass -File .\dashboard.ps1
```

It opens http://localhost:8501 (see `dashboard\README.md`). `run-all.ps1` starts it automatically.

## Interruptions

| Situation | What to do |
|---|---|
| PC restarted or Docker Desktop restarted | Start Docker Desktop and wait for "Engine running". Run the **same** command again (`run-all.ps1` for the campaign). Finished runs are skipped and failed runs retried; only the run in progress at the restart is lost. |
| You want to stop | `powershell -ExecutionPolicy Bypass -File .\stop-experiment.ps1`. Finished runs are kept. Continue later with the same `run-all` command. |
| Continue from a specific test | `run-all.ps1 -Exps E3,E4,E5` (finished runs inside them are skipped anyway) |
| Repeat one system in one test | move that system's rows out of `results\<E>_raw.csv`, then `run-all.ps1 -Exps <E> -Systems <system>` |
| Something is broken | `stop-experiment.ps1`, send the last 30 lines of the newest `results\logs\<E>-*.log` and `results\failures.log` |
| Fresh start needed during the campaign | It moves **all** results to `results-archive\`. Afterwards copy the finished `*_raw.csv` files and the `ops` folder back into `results\` before running `run-all` again, so finished runs are kept. |

---

## Step 7 — Results and statistics

**Files**

| File | Content |
|---|---|
| `results\E1_raw.csv` … `E6_raw.csv` | one row per run; columns as in TESTS.md and as in the workbook sheets `E*_raw` |
| `results\ops\*.csv` | every operation of every run |
| `results\logs\*.log` | progress log of each test and of each campaign chain |
| `results\failures.log` | runs that failed (retried at the next start) |

**Workbook:** open `OptimusDB_Section8_Evidence.xlsx`. In each sheet `E<n>_raw`, paste the rows of
`results\E<n>_raw.csv` without the header, starting at row 5. Summaries (mean, n, s.d., 95 % CI) and charts
update automatically.

**Significance tests:** run each line and paste the resulting `results\stats_*.csv` into the `Stats` sheet.

```
docker exec odb-bench python -m bench.analyze E1 --metric p99_ms --group workload doc_size
docker exec odb-bench python -m bench.analyze E1 --metric p50_ms --group workload doc_size
docker exec odb-bench python -m bench.analyze E2 --metric achieved_ops_s --group dataset_records offered_ops_s
docker exec odb-bench python -m bench.analyze E2 --metric p99_ms --group dataset_records offered_ops_s
docker exec odb-bench python -m bench.analyze E3 --metric mean_ms --group query dataset_records --key path --baseline sqlite
docker exec odb-bench python -m bench.analyze E4 --metric cpu_pct --group offered_ops_s
docker exec odb-bench python -m bench.analyze E4 --metric rss_mb --group offered_ops_s
docker exec odb-bench python -m bench.analyze E5 --metric convergence_s --group contention_pct partition_s partition_shape
docker exec odb-bench python -m bench.analyze E5 --metric write_availability_pct --group contention_pct partition_s partition_shape
docker exec odb-bench python -m bench.analyze E6 --metric e2e_p99_ms --group speed
```

**Correctness of E3:** every supported row must have `correct` = 1:

```
Import-Csv results\E3_raw.csv | Where-Object { $_.correct -ne '1' -and $_.notes -eq '' } | Format-Table system, path, query, dataset_records, rows_returned, rows_expected
```

An empty table is the expected result. Rows marked `unsupported/failed` are expected for OpenDHT on Q2–Q5.

---

## Step 8 — Archive

Keep together, unchanged:
1. the `results` folder;
2. the filled workbook `OptimusDB_Section8_Evidence.xlsx`;
3. this package (the exact scripts, harness and `versions.env` used).

Zip them and deposit the zip on Zenodo. Its DOI replaces `[TO RUN: DOI]` in Section 8.6.

---

## Command reference

| Command | Purpose |
|---|---|
| `fresh-start.ps1 [-SkipSmoke] [-Rebuild] [-DeleteResults] [-CpusEdge 1 -MemEdge 2g …]` | clean everything, redeploy, smoke-test |
| `run-all.ps1 -Pilot [-Exps E1,E2]` | pilot, results in `results\pilot\` |
| `run-all.ps1 [-Exps E1,E2,…] [-Systems a,b]` | campaign chain, unattended |
| `run-experiment.ps1 -Exp E1 [-Pilot] [-Systems a,b] [-Follow]` | one test (same as `run-all -Exps E1`) |
| `progress.ps1 [-Watch] [-Exp E3]` | progress, failures, time left |
| `stop-experiment.ps1` | stop the running test or chain; finished runs are kept |
| `status.ps1` | container state |
| `stop-local.ps1 [-Purge]` | remove the testbed (`-Purge` also deletes the data volumes) |
| `systems\deploy-<system>.ps1` | start one system on all hosts and smoke-test it (manual check) |
| `check-optimusdb.ps1` | OptimusDB runtime settings, disabled features, build, mesh |
| `diagnose-optimusdb.ps1` | OptimusDB latency with the benchmark settings vs OptimusDB defaults |
| `calibrate-baselines.ps1 [-Systems gun,autobase,opendht]` | are a baseline's failures its own behaviour or a benchmark problem? (single node vs cluster, CPU) |
| `profile-optimusdb.ps1 [-Workload WA] [-Rate 50]` | Go profile of OptimusDB under load (CPU, locks, memory); needs `pprof.go` in the build |

All are run as `powershell -ExecutionPolicy Bypass -File .\<command>`.

---

## Troubleshooting

**First step for anything that looks stuck:**

```
powershell -ExecutionPolicy Bypass -File .\diagnose.ps1
```

It is read-only and shows:
* the current step and how many minutes ago the log last moved (more than about 20 minutes is suspicious);
* which data store is running, its CPU and memory on each host;
* whether it answers on every host: an HTTP status means alive, TIMEOUT means hung, REFUSED means not running;
* recent errors in its container logs (out of memory, panics), and containers that stopped with an error;
* the last failed runs, and what to do.


| Symptom | Cause and fix |
|---|---|
| `An experiment is already running` | A test or chain is still active. Watch it with `progress.ps1`, or stop it with `stop-experiment.ps1`. |
| `The odb-bench container does not exist` | The testbed was removed. Run `fresh-start.ps1`. |
| `odb-bench is exited` | `docker start odb-bench`; if it stops again, `docker logs --tail 50 odb-bench` and send it. |
| `Docker is not running` | Start Docker Desktop and wait for "Engine running". |
| `progress.ps1` says NOT RUNNING but the campaign is not finished | The chain was interrupted (restart, stop). Run the same `run-all` command again. |
| Many `[FAILED]` lines for one system | `docker logs --tail 50 odb-cloud-a-<system>` and `odb-edge-d-<system>`; send both. |
| Ping test under 1 ms | The link profiles are missing: `docker exec odb-bench python -m bench.cluster netem --config /config/testbed.yaml`, then check again. `run-all` normally applies them. |
| Disk full | Free space on the Windows drive (the 10⁶-record cells of E2 and E3 need about 20 GB). Don't use Docker Desktop's *Clean / Purge data*: it deletes all images and volumes. |
