<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/logo-wordmark-dark.svg">
    <img src="assets/logo-wordmark.svg" alt="OptimusDB Benchmark Observatory" width="560">
  </picture>
</p>

<p align="center">
  <b>Live dashboard:</b> <a href="https://georgegeorgakakos.github.io/optimusdb-benchmark-observatory/">georgegeorgakakos.github.io/optimusdb-benchmark-observatory</a>
  &nbsp;·&nbsp; updated by <code>publish-results.ps1</code> after each run &nbsp;·&nbsp; setup: <a href="README-GITHUB.md">README-GITHUB.md</a>
</p>

---

# optimusdb-deploy — Docker Desktop testbed for the common scenarios (E1–E6): single machine or multi-host

Deploys OptimusDB and the five decentralized baselines (Corrosion, Gun.js, Autobase + Hyperbee,
Iroh docs, OpenDHT) on several **Windows machines running Docker Desktop**. A separate bench
machine runs the measurements. Every host has the same containers; only the system under test runs
at any time.

```
                 LAN (each Windows host publishes UDP 51820 only)
  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐        ┌──────────────┐
  │ bench        │   │ cloud-a      │   │ fog-a        │  ...   │ edge-d       │
  │ odb-bench-net│   │ odb-net  wg0 │   │ odb-net  wg0 │        │ odb-net  wg0 │
  │ odb-bench    │   │ odb-agent    │   │ odb-agent    │        │ odb-agent    │
  │ 10.88.0.2    │   │ 6 data stores│   │ 6 data stores│        │ 6 data stores│
  └──────────────┘   │ 10.88.0.11   │   │ 10.88.0.13   │        │ 10.88.0.18   │
        WireGuard overlay 10.88.0.0/24 between all hosts (netem + partitions act on wg0)
```

**Why an overlay.** With Docker Desktop, traffic arriving on a published port reaches the container
from Docker's internal gateway, not from the real peer. P2P systems would learn wrong peer addresses,
and per-peer delay or partition rules would not match. Each host's `odb-net` container therefore
joins a WireGuard mesh. The data stores share its network namespace, so every system sees real peer
addresses (10.88.0.x), and the Table 7 link profiles and E5 partitions are applied on `wg0`.

## 0. Single-machine mode (everything in one Docker Desktop)

**Run the evaluation: [README-RUN-GUIDE.md](README-RUN-GUIDE.md). What every test does: [TESTS.md](TESTS.md). Setup on Windows: [README-WINDOWS.md](README-WINDOWS.md).** Architecture diagram: `docs/OptimusDB_Testbed_SingleMachine.drawio` (regenerate with `python tools/build_drawio_local.py`).

The same testbed on one machine: eight emulated hosts (2 cloud, 2 fog, 4 edge), each with its own IP
(10.88.0.11–18) on a private Docker network, its own agent and the six data stores. Table 7 delays and
E5 partitions act on each emulated host's `eth0`. No `hosts.csv`, WireGuard or firewall rules are needed.

```
.\deploy-local.ps1                       # build images, generate the layout, start everything, self-test, mesh check
powershell -ExecutionPolicy Bypass -File .\fresh-start.ps1   # clean everything, redeploy, smoke-test all six (README-FRESH-START.md)
.\run-all.ps1 -Pilot                     # 2-3 h functional check, results in results\pilot\
.\run-all.ps1                            # the whole campaign E1-E5 (+E6 with a trace), unattended
.\progress.ps1 -Watch                    # progress and time left
.\stop-experiment.ps1                    # stop the campaign (finished runs are kept)
.\stop-local.ps1 [-Purge]
```

Every emulated host gets a fixed CPU and memory share for its data store: cloud/fog 2 CPUs 3 GB, edge
1 CPU 2 GB by default. Change it with `-CpusEdge 0.5 -MemEdge 1g` etc. Only the system under test
runs, so the machine needs about 12 CPUs and 20 GB for Docker at the defaults. Less works for the
pilot, but then the hosts compete for CPU. All other scripts (`systems\*`, `run-experiment`,
`netem`, `test-mesh`, `status`) work unchanged. State in the paper that the testbed is emulated
on a single host.

## 1. Prerequisites (every machine)

* Windows 10/11 (Pro or Enterprise recommended), **Docker Desktop ≥ 4.30 with the WSL2 backend**,
  Linux containers.
* Docker Desktop resources come from `%UserProfile%\.wslconfig`. On edge hosts give the VM at least
  the data-store limit plus 2 GB, e.g.
  ```
  [wsl2]
  processors=6
  memory=8GB
  ```
  then run `wsl --shutdown` and restart Docker Desktop.
* A fixed LAN IP per machine. All machines must reach each other on UDP 51820.
* The same NTP server on all hosts (`check-host.ps1 -FixTime`). Sleep must be disabled
  (`powercfg /change standby-timeout-ac 0`).
* PowerShell 7 (`winget install Microsoft.PowerShell`) is recommended. Allow local scripts once per machine:
  `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, then `Get-ChildItem -Recurse *.ps1 | Unblock-File`
  in the folder.
* About 40 GB free disk. The first build compiles Corrosion, Iroh and OpenDHT (15–30 min per host).
  You can build once and copy the images with `docker save` / `docker load`.

## 2. Configure once

1. Copy `hosts.example.csv` to `hosts.csv`. Put one row per machine: `name, role (bench|cloud|fog|edge), lan_ip`.
   * Names must **not end in a digit**, because OptimusDB treats names ending in "1" as preferred coordinators.
   * Edge rows default to Raspberry-Pi-sized limits (4 CPUs, 4 GB per data-store container, as in
     Table 7). The `ds_cpus` and `ds_mem` columns override them.
2. On any one machine, run `.\gen-config.ps1`. It writes `out\<host>\` for every host: WireGuard keys
   and config, `.env` and the agent token, plus `out\bench\config\testbed.yaml` for the harness.
3. Copy the **whole folder, including `out\`**, to every machine. `out\` contains private keys and
   the agent token, so keep it off shared drives.

## 3. Deploy

| Where | Command | What it does |
|---|---|---|
| every host | `.\check-host.ps1 -Name <host> [-FixFirewall] [-FixTime]` | Checks Docker, WireGuard/netem/iptables in the Docker VM, resources, firewall, time, sleep and disk. `-Fix*` needs an Administrator prompt. |
| every agent host | `.\deploy-host.ps1 -Name <host>` | Builds the images (OptimusDB from `OPTIMUSDB_SRC` in `versions.env`), starts `odb-net` and `odb-agent`, and creates the six data stores **stopped**. |
| bench host | `.\deploy-bench.ps1` | Starts the overlay endpoint and `odb-bench` (harness + config) and runs the harness self-test. |
| bench host | `.\test-mesh.ps1` | Every agent answers over the overlay; clock offset per host; ping matrix. |

## 4. Systems (one script each, run on the bench host)

`systems\deploy-<sys>.ps1`, `systems\stop-<sys>.ps1`, `systems\reset-<sys>.ps1` (and `.sh`), for
`<sys>` = optimusdb, corrosion, gun, autobase, iroh, opendht. All take `-Tier edge` to use only the
edge hosts.

* **deploy**: stops every other system everywhere, starts this one on all hosts, joins the nodes
  into one cluster, then writes on the first host and waits until the last host can read it.
* **reset**: as deploy, but wipes the system's data first. The harness calls it before every run.
* **stop**: stops the system and keeps its data.

How each cluster is formed (`harness/bench/cluster.py`):

| System | Join |
|---|---|
| OptimusDB | full mesh of libp2p `connect` commands to `/ip4/<overlay>/tcp/4001/p2p/<peer-id>` (mDNS does not cross the overlay) |
| Corrosion | gossip address = overlay IP:8787, bootstrap = all other hosts |
| Gun.js | each node's peer list = the other nodes' relays (`http://<overlay>:8765/gun`) |
| Autobase | first node creates the base; the others open it with its key, replicate over direct TCP (port 7305) and are added as writers and indexers |
| Iroh docs | first node creates the document; the others import its write ticket |
| OpenDHT | private network id 42; every node bootstraps from the first |

## 5. Run the common scenarios

```
.\netem.ps1                                          # Table 7 link profiles on wg0 (run-experiment does this too)
.\run-all.ps1 -Pilot                                 # pilot (2-3 h); then .\run-all.ps1 for the campaign
.\run-experiment.ps1 -Exp E1                         # campaign, in the background
.\run-experiment.ps1 -Exp E4                         # edge hosts only, Pi-sized containers
.\run-experiment.ps1 -Exp E6                         # needs trace\trace.jsonl
.\status.ps1                                         # container state on every host
.\progress.ps1 [-Watch]                              # run i of N, current step, finished runs, failures, time left
```

* Results go to `results\<E>_raw.csv` (paste them into the workbook) and `results\ops\`. Logs are in `results\logs\`.
* Failed runs are written to `results\failures.log` and retried when you start the same experiment again.

## 6. Settings that affect fairness (state them in Section 8)

* **Only the system under test runs.** Every run starts from wiped data and a freshly joined cluster
  that has passed the replication smoke test.
* **OptimusDB:** only the agent runs (no llama-server). Metadata enrichment is off, because no
  baseline has an equivalent feature. Host names avoid the preferred-coordinator rule.
* **OpenDHT:** private network, in-memory storage (its default), and `-U` (no rate limit), so the DHT
  does not throttle the benchmark.
* **Autobase:** direct TCP replication between known peers instead of Hyperswarm DHT discovery.
* **Edge hosts:** data stores are capped at 4 CPUs / 4 GB. E4 measures the cost of each system inside
  Pi-sized containers, not on physical Raspberry Pis.
* **Link profiles:** Table 7 gives cloud–cloud, cloud–fog, fog–edge and edge–edge. The generator adds
  two links Table 7 doesn't list: fog–fog (2 ms, same site) and cloud–edge (70 ms ≈ cloud–fog + fog–edge).
  Add both to Table 7.
* **Clocks:** Docker Desktop's VM follows the Windows clock, so time sync is done by Windows Time with a
  common NTP server. `test-mesh` logs the measured offset of each host.

## 7. What has been verified, and what has not

* **Verified in an emulated multi-host setup** (three Linux network namespaces with the same 10.88.0.x
  addressing, running the real `entry.sh` scripts, wrappers and agent API through `bench.cluster`):
  * cluster join and cross-host replication for **Corrosion, Gun.js, Autobase and Iroh docs**
    (Corrosion built from the pinned commit);
  * partition and heal through the agent;
  * a complete mini E1 for those four systems (28 runs, wipe and rejoin before each);
  * the E3 query path: identical Q1–Q5 row counts from Corrosion SQL and from client-side evaluation
    over Iroh docs and Autobase.

  These were functional checks only, with emulated links and tiny data, not measurements.
* **Statically checked only:** the PowerShell scripts (parsed with PowerShell 7 and run against a mock
  `docker`), the bash scripts (`bash -n`) and the compose files (`docker compose config`).
* **Not yet run anywhere:**
  * the Docker images themselves (no Docker Hub access while building this);
  * WireGuard and netem inside Docker Desktop (`check-host` tests exactly this on each machine);
  * OptimusDB and OpenDHT clusters (OptimusDB's Go modules could not be fetched here; the available dhtnode
    needs IPv6, which the emulation kernel lacks). The OptimusDB join uses the `connect` command of its HTTP API.

  The pilot (`run-all -Pilot`) is the first full test on real hardware.
* **Seen in the emulation:** under concurrent inserts, some Gun.js writes never received an
  acknowledgement within 10 s. They are recorded as errors. Check whether this persists on real
  hardware before the campaign.

## 8. Troubleshooting

| Symptom | Check |
|---|---|
| `test-mesh` shows a host unreachable | firewall rule for UDP 51820 on that host; `docker exec odb-net wg show` (a latest handshake must be listed) |
| WireGuard falls back to wireguard-go | fine; set `WG_USERSPACE=1` in that host's `.env` to force it |
| `netem` fails | `check-host` reports whether the Docker Desktop kernel has netem; update Docker Desktop |
| a system never becomes ready | `docker logs odb-<sys>` on any host, or `curl -H "x-token: <token>" http://<overlay-ip>:9100/logs/<sys>` from the bench container |
| start over | `.\stop-host.ps1 -Name <host> -Purge` on every host, then deploy again |
| hosts.csv changed | re-run `gen-config.ps1` (existing keys are kept), copy `out\` again, re-run deploy-host / deploy-bench with `-NoBuild` |

## Files

```
gen-config / check-host / deploy-host / deploy-bench / stop-host / test-mesh / netem / status / run-experiment  (.ps1 and .sh)
systems/              deploy-, stop-, reset-<system> (.ps1 and .sh)
compose/              host.compose.yml (agent hosts), bench.compose.yml (bench host)
images/               net (WireGuard/netem/iptables), agent (control API), bench, optimusdb, corrosion, gun, autobase, iroh, opendht
harness/              optimusdb-bench (benchmark harness, wrappers, tests)
tools/gen_config.py   hosts.csv -> out/<host>/ bundles and testbed.yaml
versions.env          pinned versions (OptimusDB commit, Corrosion commit, OpenDHT tag, npm and crate versions)
```
