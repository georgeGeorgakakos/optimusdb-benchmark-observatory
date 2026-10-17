# Fresh start: clean up and redeploy the testbed with one command

`fresh-start.ps1` (Windows) and `fresh-start.sh` (Linux/WSL) take the single-machine testbed from **any
state** (half-deployed, crashed, after a reboot, after updating this package) to a clean, verified testbed.
You don't need any manual or one-off Docker commands.

Use it:

* the first time you deploy;
* after you unzip a new version of this package;
* whenever something behaves oddly or a container is missing or stopped;
* right before the campaign, so every scenario starts from the same clean state.

---

## 1. Run it

Open a PowerShell window in the package folder:

```
cd C:\odb\optimusdb-deploy
```

Then run **one** of these, depending on which PowerShell you have:

| You have | Command |
|---|---|
| Windows PowerShell 5.1 (built into Windows; `pwsh` is "not recognized") | `powershell -ExecutionPolicy Bypass -File .\fresh-start.ps1` |
| PowerShell 7 (`pwsh` works) | `pwsh -ExecutionPolicy Bypass -File .\fresh-start.ps1` |
| Linux or WSL | `./fresh-start.sh` |

`-ExecutionPolicy Bypass` runs the script without the "Security warning" prompts. The script then
unblocks every other script in the folder, so later commands such as `.\run-experiment.ps1` run without
prompts too.

PowerShell 7 is optional. To install it, run `winget install --id Microsoft.PowerShell -e`, then open a new window.

---

## 2. What it does

| Step | Action | Time |
|---|---|---|
| 1 | Unblocks all `.ps1` files in the folder (files from a downloaded zip are marked as "from the internet") | seconds |
| 2 | Checks Docker Desktop and starts it if needed, waiting up to 4 minutes for "Engine running" | 0–4 min |
| 3 | Stops any running experiment inside the bench container | seconds |
| 4 | Removes every testbed container (`odb-*`), all testbed data volumes and the `odbnet` network | ~1 min |
| 5 | Moves the old `results` folder to `results-archive\<timestamp>` (nothing is deleted) | seconds |
| 6 | Builds the images. Earlier layers are reused, so this takes a few minutes; the first build ever takes 30–60 min | 2–60 min |
| 7 | Checks that `tc netem` and `iptables` work in Docker Desktop's kernel | seconds |
| 8 | Generates the layout and starts the bench, the 8 emulated hosts and their agents, and creates the 48 data-store containers (stopped) | ~1 min |
| 9 | Runs the harness self-test and the connectivity check between all hosts | ~1 min |
| 10 | Smoke-tests each of the six data stores: start on all 8 hosts, join them into one cluster, write on `cloud-a`, read on `edge-d` | ~10–15 min |
| 11 | Stops all data stores again and prints a PASS/FAIL table | seconds |

The whole run is written to `results\logs\fresh-start-<timestamp>.log`.

**Not touched:** your package files, `versions.env`, the `trace` folder, and the OptimusDB source checkout
in `.src` (unless you use `-Rebuild`).

---

## 3. Options

| Option (PowerShell) | Option (bash) | Effect |
|---|---|---|
| `-Rebuild` | `--rebuild` | Deletes the testbed images and the OptimusDB checkout, then rebuilds everything without the Docker cache (30–60 min). Use it after changing `versions.env` or if a build looks corrupted. |
| `-DeleteResults` | `--delete-results` | Deletes old results instead of archiving them. |
| `-SkipSmoke` | `--skip-smoke` | Skips step 10 (saves ~15 min). |
| `-CpusCloud 1.5 -MemCloud 3g` | `--cpus-cloud 1.5 --mem-cloud 3g` | CPU / memory limit per data store on cloud hosts. |
| `-CpusFog 1.5 -MemFog 3g` | `--cpus-fog 1.5 --mem-fog 3g` | The same for fog hosts. |
| `-CpusEdge 1 -MemEdge 2g` | `--cpus-edge 1 --mem-edge 2g` | The same for edge hosts. |

**Limits are remembered.** Without limit options, the script reuses the limits of the previous deployment.
If there is no previous deployment, it uses cloud and fog 1.5 CPU / 3 GB and edge 1 CPU / 2 GB. These
defaults fit a Docker Desktop VM with 12 CPUs. While one system runs, the testbed needs about 11.5 CPUs.

Examples:

```
powershell -ExecutionPolicy Bypass -File .\fresh-start.ps1                           # normal fresh start
powershell -ExecutionPolicy Bypass -File .\fresh-start.ps1 -Rebuild                  # everything from scratch
powershell -ExecutionPolicy Bypass -File .\fresh-start.ps1 -CpusEdge 0.5 -MemEdge 1g # smaller edge hosts
```

---

## 4. Reading the result

A successful run ends like this:

```
==> Smoke test summary
  System     Result Visible on last host (s)
  optimusdb  PASS   2.41
  corrosion  PASS   1.02
  gun        PASS   0.87
  autobase   PASS   1.65
  iroh       PASS   1.30
  opendht    PASS   0.95
  [OK]   All six data stores form a cluster and replicate

Fresh testbed ready. Next:  .\run-all.ps1 -Pilot   then   .\progress.ps1 -Watch
Log: results\logs\fresh-start-20261012-200102.log
```

The numbers above are only an illustration. **Visible on last host** is the time from the write on
`cloud-a` until `edge-d` could read it, with no link emulation applied yet.

| Outcome | What to do |
|---|---|
| All rows PASS | Continue with the pilot: `powershell -ExecutionPolicy Bypass -File .\run-all.ps1 -Pilot` |
| One or more rows FAIL | The testbed is up, but don't start the campaign. Send the log file and the output of `docker logs --tail 50 odb-cloud-a-<system>` and `docker logs --tail 50 odb-edge-d-<system>` for each failed system. |
| The script stops with an error before the table | Read the last red lines; the table below covers the common cases. Send the log file if it isn't one of them. |

---

## 5. Troubleshooting

| Message | Cause and fix |
|---|---|
| `pwsh : The term 'pwsh' is not recognized` | PowerShell 7 isn't installed. Use `powershell -ExecutionPolicy Bypass -File .\fresh-start.ps1` instead. |
| `Docker Desktop was not found at ...` | Docker Desktop is installed somewhere non-standard. Start it by hand, wait for "Engine running", and run the script again. |
| `Docker Desktop did not become ready within 4 minutes` | Docker Desktop is still starting or is stuck. Open it, wait for "Engine running" (restart it from the tray icon if needed), then run again. |
| `Docker Desktop must use Linux containers` | Right-click the Docker tray icon → *Switch to Linux containers*. |
| `tc netem not available` / `iptables not available` | Docker Desktop's kernel lacks the module. Update Docker Desktop. Without netem, Table 7 link profiles can't be applied; without iptables, E5 partitions fail. |
| A `docker build ... failed` line | Usually a network problem during the build, or a full disk. Check free space (about 40 GB needed), then run again. If the same image fails twice, run with `-Rebuild` and send the log if it still fails. |
| `Harness self-test` fails | Send the log file. |
| The PC slept during the run | Run the script again; it starts from a clean state each time. Set sleep to *Never* (README-WINDOWS.md, Part A6). |

---

## 6. Where your old data goes

| Before | After a fresh start |
|---|---|
| `results\` (raw CSVs, ops, logs) | moved to `results-archive\<timestamp>\`, then a new empty `results\` is created |
| data inside the data stores (Docker volumes) | deleted; every experiment run wipes and reloads data anyway |
| Docker images | kept and reused (deleted only with `-Rebuild`) |
| `.src\optimusdb` (OptimusDB checkout) | kept, and updated to the commit in `versions.env` (deleted only with `-Rebuild`) |

To continue an interrupted campaign **without** losing its progress, **don't** run a fresh start.
Run the same `run-experiment` command again: finished runs are skipped. If you have already run a fresh
start, copy `results-archive\<timestamp>\*_raw.csv` back into `results\` before restarting the
scenario, and the harness will continue from there.
