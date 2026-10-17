# Running the OptimusDB evaluation on one Windows PC (Docker Desktop)

> Setup is described here. For running the tests use [README-RUN-GUIDE.md](README-RUN-GUIDE.md); every test is specified in [TESTS.md](TESTS.md).

This guide walks through every step on a single Windows 10/11 machine: from a clean PC to the
result files of the common scenarios E1–E6. Commands go in **PowerShell**; lines starting with `PS>`
are commands to type (without the `PS>`).

What you will end up with: one Docker Desktop running 8 emulated hosts (cloud-a, cloud-b, fog-a,
fog-b, edge-a … edge-d), each with its own IP (10.88.0.11–18), a control agent and the six data
stores (OptimusDB, Corrosion, Gun.js, Autobase, Iroh docs, OpenDHT), plus one `odb-bench` container
that runs the experiments. Only one data store runs at a time.

---

## Part A — Prepare Windows (once, about 30 minutes)

### A1. Check the machine

| Item | Minimum for the pilot | Recommended for the campaign |
|---|---|---|
| CPU | 8 logical cores | 16 or more |
| RAM | 16 GB | 32 GB or more |
| Free disk on the drive you will use | 60 GB | 100 GB (SSD) |
| Windows | 10 22H2 or 11, 64-bit | 11 Pro |

Check your cores and RAM: press **Ctrl+Shift+Esc** → **Performance** → **CPU** ("Logical processors")
and **Memory**.

Virtualization must be enabled. In Task Manager → Performance → CPU, "Virtualization" must say
**Enabled**. If it says Disabled, enable Intel VT-x or AMD-V (SVM) in the BIOS/UEFI setup.

### A2. Install WSL2

Open **PowerShell as Administrator** (Start → type *PowerShell* → right-click → *Run as administrator*):

```
PS> wsl --install --no-distribution
PS> wsl --update
```

Restart Windows if asked. Check:

```
PS> wsl --status
```

It must show "Default Version: 2".

### A3. Install PowerShell 7 and Docker Desktop

Still in the Administrator PowerShell:

```
PS> winget install --id Microsoft.PowerShell -e
PS> winget install --id Docker.DockerDesktop -e
```

(If `winget` is missing, install **App Installer** from the Microsoft Store, or download Docker
Desktop from docker.com and PowerShell 7 from github.com/PowerShell/PowerShell/releases.)

Restart Windows. Start **Docker Desktop**, accept the licence and skip the sign-in if you like.

### A4. Configure Docker Desktop

In Docker Desktop, click the **gear icon (Settings)**:

1. **General**:
   * ✅ *Use the WSL 2 based engine*
   * ✅ *Start Docker Desktop when you sign in to your computer*. Optional, but it lets the testbed
     come back after a reboot.
2. **Resources → WSL integration**: leave the defaults.
3. Click **Apply & restart**.

Check that Docker runs Linux containers. In a normal PowerShell 7 window (Start → *PowerShell 7*):

```
PS> docker version --format '{{.Server.Os}}'
linux
PS> docker run --rm hello-world
```

If the first command prints `windows`, right-click the Docker whale icon in the system tray and
choose **Switch to Linux containers…**.

### A5. Give Docker enough CPU and memory

Docker Desktop on WSL2 takes its CPU and memory limits from the file `%UserProfile%\.wslconfig`.

```
PS> notepad $env:USERPROFILE\.wslconfig
```

Notepad asks to create the file; click **Yes** and paste the block below. Choose values for your machine:
* `processors` = all logical cores minus 2 (keep 2 for Windows);
* `memory` = RAM minus 6 GB.

```
[wsl2]
processors=14
memory=26GB
swap=8GB
```

Save, close Notepad, then apply:

```
PS> wsl --shutdown
```

Wait 10 seconds and start Docker Desktop again. Check what Docker now sees:

```
PS> docker info --format '{{.NCPU}} CPUs, {{.MemTotal}} bytes'
```

### A6. Keep the PC awake during long runs

Administrator PowerShell:

```
PS> powercfg /change standby-timeout-ac 0
PS> powercfg /change hibernate-timeout-ac 0
```

Keep the laptop plugged in. Also pause Windows Update for the campaign: **Settings → Windows Update → Pause updates**.

---

## Part B — Get the package (5 minutes)

### B1. Unpack to a short local path

Extract `optimusdb-deploy.zip` to **`C:\odb`**, so that you have `C:\odb\optimusdb-deploy\deploy-local.ps1`.

* **Do not** use a OneDrive, Dropbox or network folder. Docker mounts this folder, and sync tools
  lock or rewrite files.
* Keep the path short and without spaces.

### B2. Allow the scripts to run

Open **PowerShell 7** (not as Administrator) and run:

```
PS> cd C:\odb\optimusdb-deploy
PS> Set-ExecutionPolicy -Scope CurrentUser RemoteSigned      # answer Y
PS> Get-ChildItem -Recurse *.ps1 | Unblock-File
```

### B3. Check where OptimusDB is built from

Open `versions.env` (e.g. `notepad versions.env`). The line

```
OPTIMUSDB_SRC=https://github.com/georgeGeorgakakos/optimusdb.git#233eae27c172674991b1efb08f8e0f2b324691f6
```

builds OptimusDB from your GitHub repository at that commit. `deploy-local` first clones the repository into `.src\optimusdb`, using git inside a container, so you don't need git on Windows. It then builds from that checkout. Docker cannot build straight from the URL, because the repository contains a submodule entry (`binding/go-llama.cpp`) without a `.gitmodules` URL.

* **If the repository is private**, or you want to test local changes, clone it and point to the
  folder instead:
  ```
  OPTIMUSDB_SRC=C:\odb\optimusdb
  ```
  (`git clone https://github.com/georgeGeorgakakos/optimusdb.git C:\odb\optimusdb`)
* **Before the real campaign**, replace the commit with the release you want to report. Put the same
  commit in Table 9 of the paper.

---

## Part C — Build and start the testbed

### C1. Deploy

```
PS> cd C:\odb\optimusdb-deploy
PS> .\deploy-local.ps1
```

What happens, and how long it takes:

| Stage | Output starts with | Time (first run) |
|---|---|---|
| resource check | `==> Docker Desktop VM: … CPUs` | seconds |
| image builds | `==> Building images` | 30–60 min (Corrosion, Iroh, OpenDHT compile from source) |
| kernel check | `[OK] tc netem available`, `[OK] iptables available` | seconds |
| layout | a table of the 8 hosts with their IPs and limits | seconds |
| start | `Starting bench, 8 emulated hosts and their agents` | ~1 min |
| create | `Creating 48 data-store containers (stopped)` | ~1 min |
| self-test | `12 passed` and `[OK] Harness self-test passed` | ~30 s |
| mesh check | one JSON block per host with `pings` to every other host | ~30 s |

**If the machine is smaller than the defaults need** (about 12 CPUs), a warning appears. For the
pilot, lower the limits:

```
PS> .\deploy-local.ps1 -NoBuild -CpusCloud 1 -MemCloud 2g -CpusFog 1 -MemFog 2g -CpusEdge 0.5 -MemEdge 1g
```

Use the **same limits for all systems and all experiments**, and report them in the paper.

**Later runs:** add `-NoBuild` to skip the image builds (seconds instead of an hour).

### C2. What you should see in Docker Desktop

**Containers** view → group **odb-local**:

* **Running**: `odb-bench`, `odb-<host>-net` and `odb-<host>-agent` for the 8 hosts (17 containers).
* **Created / Exited**: `odb-<host>-<system>`, 48 containers. They are started on demand.

From PowerShell:

```
PS> .\status.ps1          # state of every container, per emulated host
PS> .\test-mesh.ps1       # ping matrix and clock offsets between the emulated hosts
```

---

## Part D — Smoke-test each data store (about 15 minutes)

Run these one after the other. Each one stops the others, starts that system on all 8 hosts, joins
them into one cluster, writes a test record on `cloud-a` and waits until `edge-d` can read it.

```
PS> .\systems\deploy-gun.ps1
PS> .\systems\deploy-corrosion.ps1
PS> .\systems\deploy-autobase.ps1
PS> .\systems\deploy-iroh.ps1
PS> .\systems\deploy-opendht.ps1
PS> .\systems\deploy-optimusdb.ps1
```

A successful run ends with JSON like:

```
{ "system": "corrosion", "hosts": ["cloud-a", …, "edge-d"], "smoke_s": 1.02 }
```

`smoke_s` = seconds until the write was visible on the last host.

**If one fails**, look at its log on any host and send me the last lines:

```
PS> docker logs --tail 50 odb-cloud-a-optimusdb
PS> docker logs --tail 50 odb-edge-d-optimusdb
```

Other per-system scripts: `systems\stop-<system>.ps1` (stop, keep data) and
`systems\reset-<system>.ps1` (wipe data, start, join, smoke test).

---

## Part E — Pilot (about 2–3 hours, unattended)

The pilot is a quick functional check of the whole pipeline. It is **not** used in the paper and its
results go to `results\pilot\`, separate from the campaign.

```
PS> powershell -ExecutionPolicy Bypass -File .\run-all.ps1 -Pilot
PS> powershell -ExecutionPolicy Bypass -File .\progress.ps1 -Watch
```

* `run-all` applies the Table 7 link profiles, starts the pilot inside the bench container and returns.
  You can close the window; only the PC must stay awake.
* Pilot settings: 1 repetition, 30 s warm-up + 120 s measured, E1 on 5 cells per system (WA, WB, WC, WO at
  2 KB, and WO at 8 KB), so 30 runs of about 5 minutes each.
* `progress.ps1 -Watch` shows run *i* of 30, the current step, finished runs per system, failures and
  the estimated finish time.

When it has finished, check:

```
PS> Import-Csv results\pilot\E1_raw.csv | Format-Table system, workload, doc_size, p50_ms, p99_ms, errors
PS> Get-Content results\pilot\failures.log      # should be empty or nearly so
```

Before the campaign:
* If a system shows many `errors`, check its log as in Part D.
* If the CPU is constantly at 100% (Task Manager → *Vmmem* / *VmmemWSL*), lower the limits with
  `fresh-start.ps1 -CpusEdge ...` and repeat the pilot.
* To pilot the other scenarios too: `.\run-all.ps1 -Pilot -Exps E1,E2,E3,E4,E5` (much longer).

---

## Part F — The campaign (E1–E6), one command

```
PS> powershell -ExecutionPolicy Bypass -File .\run-all.ps1
```

This runs E1 → E2 → E3 → E4 → E5 one after the other, unattended, and E6 as well if
`trace\trace.jsonl` exists. Each scenario uses the paper's settings (10 repetitions for E1, 300 s measured
after 60 s warm-up). For E1, documents up to 8 KB use 10⁵ records; 64 KB documents use 12,500 records,
so the dataset stays at about 800 MB per replica. **State this in Section 8.**

| Scenario | Rough duration on one PC |
|---|---|
| E1 latency (6 systems × 7 cells × 10 reps) | ~2.5–3 days |
| E2 throughput and data volume | ~2–3 days |
| E3 queries (10⁶-record loads dominate) | ~1–2 days |
| E4 resource cost (edge hosts only) | ~1 day |
| E5 partitions | ~3 days |
| E6 trace replay | depends on the trace (≈ 30 h for a 4-hour trace) |

Only one chain can run at a time; `run-all` refuses to start a second one.

Other forms:

```
PS> .\run-all.ps1 -Exps E3,E4                   # only some scenarios
PS> .\run-all.ps1 -Exps E5 -Systems corrosion   # repeat one system
PS> .\run-all.ps1 -Exps E6                      # after the trace has been captured
PS> .\stop-experiment.ps1                       # stop (finished runs are kept)
```

**Watch progress:**

```
PS> .\progress.ps1            # running or not, run i of N, current step, finished runs per system, failures, time left
PS> .\progress.ps1 -Watch     # the same, refreshed every 30 s (Ctrl+C stops watching; the experiment keeps running)
```

The experiment log (`results\logs\<E>-<time>.log`) has one line per step of every run:
`[12/84] gun WO 8KB rep 1`, `reset ...`, `loading ...`, `measuring ...`, `done ...: p50=... p99=...`.

**After a reboot or crash:** start Docker Desktop. The bench, net and agent containers restart on
their own, but the chain does not. Run the same `run-all` command again: finished runs are skipped and
failed runs (`results\failures.log`) are retried.

---

## Part G — Results

| File | Content |
|---|---|
| `results\E1_raw.csv` … `E6_raw.csv` | one row per run, exactly the columns of the workbook sheets `E*_raw` |
| `results\ops\*.csv` | every operation of every run (for CDFs and re-analysis) |
| `results\logs\*.log` | console output of each scenario |
| `results\failures.log` | runs that failed and will be retried |

1. Open `OptimusDB_Section8_Evidence.xlsx`. In sheet `E1_raw`, paste the rows of `results\E1_raw.csv`
   (without its header) starting at row 5. Summaries and charts update automatically.
2. Statistics per scenario (OptimusDB against each baseline, Welch or Mann-Whitney test, Holm correction,
   Cliff's delta). Each command writes `results\stats_<E>_<metric>.csv` and `results\cdf_<E>.csv`;
   paste them into the `Stats` sheet.
   ```
   PS> docker exec odb-bench python -m bench.analyze E1 --metric p99_ms --group workload doc_size
   PS> docker exec odb-bench python -m bench.analyze E1 --metric p50_ms --group workload doc_size
   PS> docker exec odb-bench python -m bench.analyze E2 --metric achieved_ops_s --group dataset_records offered_ops_s
   PS> docker exec odb-bench python -m bench.analyze E2 --metric p99_ms --group dataset_records offered_ops_s
   PS> docker exec odb-bench python -m bench.analyze E3 --metric mean_ms --group query dataset_records --key path --baseline sqlite
   PS> docker exec odb-bench python -m bench.analyze E4 --metric cpu_pct --group offered_ops_s
   PS> docker exec odb-bench python -m bench.analyze E4 --metric rss_mb --group offered_ops_s
   PS> docker exec odb-bench python -m bench.analyze E5 --metric convergence_s --group contention_pct partition_s partition_shape
   PS> docker exec odb-bench python -m bench.analyze E5 --metric write_availability_pct --group contention_pct partition_s partition_shape
   PS> docker exec odb-bench python -m bench.analyze E6 --metric e2e_p99_ms --group speed
   ```
   E3 compares query paths rather than systems (OptimusDB has two: `crdt` and `sqlite`); also check the
   `correct` column of `E3_raw.csv`, which must be 1 for every row.
3. Keep the `results` folder, the workbook and this package together. They are the artefact you will
   archive (Zenodo DOI) and cite in Section 8.6.

---

## Fresh start (one command, from any state)

Use this whenever something is in an unknown state, after updating the package, or before the campaign.
Open PowerShell in the package folder and run:

```
powershell -ExecutionPolicy Bypass -File .\fresh-start.ps1     # Windows PowerShell 5.1
pwsh -ExecutionPolicy Bypass -File .\fresh-start.ps1           # PowerShell 7, if installed
```

Full guide: [README-FRESH-START.md](README-FRESH-START.md).

It does everything below by itself and logs to `results\logs\fresh-start-<timestamp>.log`:

1. unblocks all scripts (no more security prompts afterwards);
2. starts Docker Desktop if needed and waits until it is ready;
3. stops any running experiment and removes every testbed container, data volume and the network;
4. moves old results to `results-archive\<timestamp>` (nothing is deleted);
5. builds the images (cached, a few minutes) and starts the testbed with the same CPU/memory limits as last time;
6. smoke-tests all six data stores and prints a PASS/FAIL table.

| Option | Effect |
|---|---|
| `-Rebuild` | rebuild every image from scratch and re-clone OptimusDB (30–60 min) |
| `-DeleteResults` | delete old results instead of archiving them |
| `-SkipSmoke` | skip the six smoke tests |
| `-CpusEdge 1 -MemEdge 2g` (etc.) | change the limits; they are remembered for the next fresh start |

When every row says PASS, continue with Part E (pilot). If a row says FAIL, send me the log file.

---

## Part H — Stop, clean up, start over

```
PS> .\stop-local.ps1            # stop and remove containers, keep data volumes
PS> .\stop-local.ps1 -Purge     # also delete all data volumes
PS> .\deploy-local.ps1 -NoBuild # bring everything back
```

To free disk space after the campaign: Docker Desktop → **Images** → delete the `odb-*` images,
or `docker system prune -a`.

---

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `Docker Desktop is not running` | Start Docker Desktop and wait until the whale icon stops animating. |
| `Docker Desktop must use Linux containers` | Tray icon → *Switch to Linux containers…* |
| Running the script shows `… cannot be loaded because running scripts is disabled` | Part B2 (`Set-ExecutionPolicy`, `Unblock-File`). |
| Build fails at `Cloning …` or `odb-optimusdb-base` with an authentication error | The repository is private: clone it locally and set `OPTIMUSDB_SRC` to the folder (Part B3). |
| Build fails while downloading (timeouts, `TLS`, `proxy`) | Corporate proxy or firewall: set the proxy in Docker Desktop → Settings → Resources → Proxies, or build at home. |
| `[FAIL] tc netem not available` | Update Docker Desktop (Settings → Software updates). Without netem the delays of Table 7 cannot be applied. |
| `Pool overlaps with other one on this host` / network error at start | The 10.88.0.0/24 range is in use on your network: `.\stop-local.ps1`, then `.\deploy-local.ps1 -NoBuild -Subnet 10.77.0`. |
| A smoke test times out | `docker logs --tail 50 odb-cloud-a-<system>` and `odb-edge-d-<system>`, then send me the output. |
| PC becomes very slow, *VmmemWSL* uses all memory | Lower `memory` in `.wslconfig` or the per-host limits (`-Mem*`), run `wsl --shutdown`, restart Docker Desktop. |
| Disk full | `docker system df`; delete old results/ops files you have archived; `docker builder prune`. |
| Results look odd after Windows went to sleep | Sleep pauses the VM and distorts timings. Delete the affected rows from `results\E*_raw.csv` (they will be rerun) and apply Part A6. |

## What to write in the paper about this setup

* **Testbed (Table 7):** one Windows PC (CPU model, cores, RAM, SSD), Docker Desktop on WSL2. Eight
  emulated hosts on a Docker bridge network. Per-host limits: cloud/fog X CPUs and Y GB, edge Z CPUs
  and W GB. Table 7 link profiles via tc/netem, including the derived fog–fog (2 ms) and cloud–edge
  (70 ms) links.
* **Threats to validity:**
  * all hosts share one physical machine (mitigated by fixed CPU and memory limits, and by running only
    the system under test);
  * all network effects are emulated;
  * E4 measures resource cost inside capped containers rather than on Raspberry Pi hardware.
