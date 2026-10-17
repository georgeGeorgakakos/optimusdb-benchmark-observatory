# Test specification: the common scenarios E1–E6

This document describes every test the harness runs in the single-machine testbed: what it measures, the
exact factor levels, the step-by-step procedure, how each metric is computed, and what is written to the
result files. Every value in it is taken from the harness code in `harness/bench/`, so it describes what
actually runs, not an intention. E7–E11 (OptimusDB-only mechanisms) are not covered here.

Contents

1. [Common setup (applies to every test)](#1-common-setup-applies-to-every-test)
2. [E1 — Latency and tail behaviour](#2-e1--latency-and-tail-behaviour)
3. [E2 — Throughput and data volume](#3-e2--throughput-and-data-volume)
4. [E3 — Query expressiveness and cost](#4-e3--query-expressiveness-and-cost)
5. [E4 — Edge resource cost](#5-e4--edge-resource-cost)
6. [E5 — Partitions, contention and convergence](#6-e5--partitions-contention-and-convergence)
7. [E6 — Operational trace replay](#7-e6--operational-trace-replay)
8. [Pilot mode](#8-pilot-mode)
9. [Statistical analysis](#9-statistical-analysis)
10. [Run counts and durations](#10-run-counts-and-durations)
11. [Known limitations and risks](#11-known-limitations-and-risks)
12. [What Section 8 of the paper must state](#12-what-section-8-of-the-paper-must-state)

---

## 1. Common setup (applies to every test)

### 1.1 Testbed

| Item | Value |
|---|---|
| Machine | one Windows PC, Docker Desktop (WSL2 back end) |
| Emulated hosts | 8: `cloud-a`, `cloud-b` (cloud), `fog-a`, `fog-b` (fog), `edge-a` … `edge-d` (edge) |
| Addresses | Docker bridge `odbnet`, 10.88.0.0/24; hosts 10.88.0.11–.18 in the order above; benchmark client (`bench`) 10.88.0.2 |
| Per host | one network container (own IP, `tc`, `iptables`), one control agent (port 9100), six data-store containers sharing that network namespace |
| Limits per data store | cloud and fog: 1.5 CPU, 3 GB; edge: 1 CPU, 2 GB (Docker `cpus` / `mem_limit`) |
| Systems | OptimusDB, Corrosion, Gun.js, Autobase + Hyperbee, Iroh docs, OpenDHT (versions in `versions.env`) |
| Isolation | only the system under test runs; the other five are stopped on every host |

### 1.2 Emulated network (Table 7)

Applied once by `run-all` / `run-experiment` with `tc` on `eth0` of every emulated host. Each host has
one HTB class per destination tier, with `netem` delay, jitter (normal distribution), loss, and an HTB
rate cap. The rules shape **outgoing** packets only, so every value below is **one-way**. A request and
its reply each pay it once, so the round trip is about twice the delay.

| Link | One-way delay | Jitter | Loss per direction | Rate | Source |
|---|---|---|---|---|---|
| cloud–cloud | 5 ms | ±1 ms | 0 % | 1 Gbit/s | Table 7 |
| cloud–fog | 20 ms | ±4 ms | 0.1 % | 100 Mbit/s | Table 7 |
| fog–fog | 2 ms | ±0.5 ms | 0 % | 1 Gbit/s | derived (same site) |
| fog–edge | 50 ms | ±10 ms | 0.5 % | 10 Mbit/s | Table 7 |
| cloud–edge | 70 ms | ±11 ms | 0.6 % | 10 Mbit/s | derived (cloud–fog + fog–edge) |
| edge–edge | 2 ms | ±0.5 ms | 0 % | 100 Mbit/s | Table 7 |

Traffic between the benchmark client and the host it talks to is **not** delayed (it falls in the default
class), so the client behaves as if it ran next to that host.

### 1.3 Where the client sends requests

| Test | Entry host | Other hosts used |
|---|---|---|
| E1, E2, E3 | `cloud-a` | all 8 hosts are in the cluster; replication and remote reads cross the emulated links |
| E4 | `edge-a` | the system runs on the 4 edge hosts only |
| E5 | every host (one writer per host) | all 8 |
| E6 | the host named in each trace event | all 8 |

### 1.4 Load once, run many (blocks), and the reset

The tests follow YCSB's load phase / run phase method. A **block** is one deployment of one system with one
dataset (for example Gun.js with 10⁵ records of 2 KB). Each block starts with a reset and one preload, then
all runs of that block follow on the same data, in random order. Each run has its own warm-up and measured
window.

| Test | One block = | Runs in a block |
|---|---|---|
| E1 | system × document size | 2 KB: 4 workloads × 10 reps = 40; 256 B / 8 KB / 64 KB: 10 each |
| E2 | system × dataset size | 10⁵: 5 load-step series; 10³, 10⁴, 10⁶: 5 runs each |
| E3 | target × dataset size | 5 queries × 10 reps (queries do not change data) |
| E4 | system (edge hosts) | 4 levels × 5 reps |
| E5 | system | all its cells × 10 reps |

* **Data drift:** writes in earlier runs change the data a later run sees. Updates keep the dataset size.
  Inserts (WO only) re-use the same new keys in every run with the same repetition number, so the dataset
  grows by at most about 1.5 % (E1 at 10⁵ records).
* **Run order:** `seq` in the E1 `notes` gives each run's position in its block, so order effects can be checked.
* **Reload after a failure:** if a run fails, the system is reset and reloaded before the next run of that
  block. In E5 this also happens after any run whose replicas did not converge within 600 s.

A **reset** (at the start of each block) does the following:

1. stops every data store on every host;
2. wipes the data volumes of the system under test on the hosts it will use;
3. starts it on those hosts and joins them into one cluster (join method per system in `README.md`, section 4);
4. runs a replication smoke test: writes one document on the first host and polls the last host once per
   second until it can read it (timeout 120 s). If this fails, the run fails and is retried later.

The smoke document (`smoke-<random>`, region `eu-west`, status `Stopped`, 2 CPUs, 2 GB) stays in the store.
It matches none of the E3 predicates, so it does not change any expected row count.

### 1.4a Preload and replication before measuring

Every test that preloads data (E1–E5) does it the same way, for every system:

1. The link profiles are removed for the duration of the preload. The preload is not measured; pushing it
   through the emulated WAN only made runs longer, and it stalled Iroh docs' replication in the pilot.
2. The records (and for E3, the allocations) are bulk-loaded through the entry host.
3. The harness waits until a fixed random sample of 200 preloaded keys can be read **locally on every host**
   of the deployment (polled every 5 s, timeout 900 s). OptimusDB replicas are read with `LOCAL_ONLY`.
4. The link profiles are applied again, and only then do the warm-up and the measured window start.

Every measured window therefore starts from a fully replicated dataset on the emulated WAN. The wait is
written to `notes` in E1 as `settled=<s>s`, or `settled=timeout` if the sample was not complete after 900 s
(the run is then measured anyway and the note marks it).

### 1.5 Data model

Each record is a JSON resource descriptor with key `res-000000000`, `res-000000001`, …:

| Field | Values | Derived from record number *i* |
|---|---|---|
| `_id` | `res-` + 9 digits | *i* |
| `region` | eu-west, eu-central, eu-south, eu-north | *i* mod 4 |
| `cpu_capacity` | 2, 4, 8, 16 | ⌊*i*/4⌋ mod 4 |
| `memory_capacity` | 2048, 4096, 8192, 16384 | ⌊*i*/16⌋ mod 4 |
| `status` | Running, Stopped, Pending, Degraded | (⌊*i*/64⌋ + version) mod 4 |
| `resource_provider` | AWS, Azure, GCP, OnPrem | ⌊*i*/256⌋ mod 4 |
| `resource_type` | Cloud, Fog, Edge | *i* mod 3 |
| `storage` | 100 … 1000 | 100 × (1 + *i* mod 10) |
| `version`, `writer_ts` | update counter, client timestamp at write | — |
| `payload` | random letters | pads the JSON to the target size |

The fields use independent base-4 digits of *i*, so the predicates are uncorrelated: each of region, CPU,
memory and status splits the data into quarters. Document sizes: 256 B, 2 KB, 8 KB, 64 KB (JSON bytes).

### 1.6 Workloads (YCSB-style)

| Id | Read | Update | Insert | Query | Description |
|---|---|---|---|---|---|
| WA | 50 % | 50 % | — | — | YCSB-A, update-heavy |
| WB | 95 % | 5 % | — | — | YCSB-B, read-mostly |
| WC | 100 % | — | — | — | YCSB-C, read-only |
| WO | 60 % | 20 % | 10 % | 10 % | orchestration mix: status reads, status updates, new descriptors, matchmaking queries |

* **Key choice:** scrambled Zipfian with θ = 0.99 (YCSB generator), so hot keys are spread across the key space.
* **Read:** fetch one document by key.
* **Update:** overwrite a whole document with a new version.
* **Insert:** a new key beyond the preloaded range.
* **Query (WO only):** documents with `region` = a random region and `status` = `Running`. This matches about
  1/16 of the records (6,250 at 10⁵). OpenDHT cannot run it (see 11.3).
* The random seed of each run is its repetition number, so repetition *r* issues the same operation
  sequence on every system.

### 1.7 Load generator and timing

* **Open loop:** requests are issued on a schedule, whether or not earlier requests have finished. Arrivals
  are Poisson at the offered rate.
* **Latency** of an operation = completion time − **scheduled** start time. A slow system therefore cannot
  hide queueing delay (no coordinated omission).
* **Per-operation timeout:** 10 s. A timeout or any error counts as a failed operation.
* **Overload guard:** at most 2,000 operations are in flight. A scheduled operation that finds 2,000 already
  outstanding is not issued and is counted as `dropped` (written to `notes`).
* **Warm-up:** operations scheduled during the warm-up are executed but not recorded.

### 1.8 Per-run metrics (written by every load-driven test)

| Metric | Definition |
|---|---|
| `ops` | operations scheduled in the measured window and issued |
| `errors` | failed operations (error, timeout, unsupported) |
| `mean_ms`, `p50_ms`, `p95_ms`, `p99_ms`, `p999_ms` | over **successful** operations only |
| `achieved_ops_s` | successful operations ÷ measured seconds |

Times in the progress logs are the containers' clock, which is UTC (Athens time minus 3 hours in summer).

Every operation of every run is also written to `results/ops/<run_id>.csv` (scheduled, start and end time,
kind, ok, error), for latency distributions and re-analysis.

### 1.9 Order of runs and resuming

* The order of the blocks, and the order of the runs inside each block, are shuffled with a fixed seed
  (20261101). In E2, E3 and E4 the repetitions inside a block run in ascending order.
* Runs of one system are therefore consecutive (one block), not interleaved with other systems' runs.
  Slow drifts of the machine show up as differences between blocks; the start time of every run is
  recorded (`start_utc`, and the log), so such drifts can be examined.
* **Resuming:** each finished run is identified by its `run_id`. A run already present in
  `results/<E>_raw.csv` is skipped when the test starts again.
* **Failed runs** go to `results/failures.log` and are not written to the CSV, so a restart retries them.

---

## 2. E1 — Latency and tail behaviour

| | |
|---|---|
| Question | How fast does each system answer at a moderate, steady load, including the slowest requests? |
| RQ / contribution | RQ2; C1, C3 |
| Hypothesis H1 | For WO, OptimusDB's P99 latency is within 25 % of the best baseline, and its tail ratio P99.9/P50 is not larger than the median of the baselines. |
| Systems | all six |
| Paper figure | F1 |

**Factors and levels**

| Factor | Levels |
|---|---|
| System | 6 |
| Workload at 2 KB | WA, WB, WC, WO |
| Document size (WO only) | 256 B, 8 KB, 64 KB (plus 2 KB from the row above) |
| Records preloaded | 10⁵ for 256 B, 2 KB and 8 KB; **12,500 for 64 KB** (volume capped at 10⁵ × 8 KB ≈ 800 MB per replica) |
| Offered load | 50 ops/s, Poisson |
| Warm-up / measured | 60 s / 300 s (≈ 15,000 measured operations) |
| Repetitions | 10 |

Cells: 7 per system (WA, WB, WC, WO at 2 KB; WO at 256 B, 8 KB, 64 KB), 42 in total → **420 runs**.

**Procedure**

For each block (system × document size), in shuffled order:
1. Reset the system (section 1.4) on all 8 hosts.
2. Preload the records through `cloud-a` (bulk requests of up to ~4 MB each) and wait until they are on every
   host (section 1.4a).
3. For each run of the block, in shuffled order: run the workload against `cloud-a` for 60 s warm-up + 300 s
   measured; write one row to `results/E1_raw.csv` and the operations to
   `results/ops/E1-<system>-<workload>-<size>-<rep>.csv`.

24 blocks (6 systems × 4 sizes), so 24 preloads for 420 runs.

**System settings that matter here**
* **OptimusDB:** reads and queries use strategy `LOCAL_THEN_REMOTE_MERGE`, consistency `BEST_EFFORT`, time
  budget 1,200 ms: the local replica answers, and peers are asked only when it has no matching rows. Reads
  and updates by `_id` use the index entry directly. Metadata enrichment is off.
* **The other systems:** reads and writes through their native API or the HTTP wrapper on `cloud-a`.

**Output columns (`E1_raw.csv`):** run_id, system, workload, doc_size, rep, ops, errors, mean_ms, p50_ms,
p95_ms, p99_ms, p999_ms, achieved_ops_s, start_utc, notes (`dropped=<n> records=<n> settled=<s>s seq=<position in block>`).

---

## 3. E2 — Throughput and data volume

| | |
|---|---|
| Question | How much load can each system sustain, and how does latency change as the dataset grows? |
| RQ / contribution | RQ2; C1 |
| Hypothesis H2 | OptimusDB's saturation throughput is at least the median of the baselines, and its P99 at 50 ops/s grows by less than a factor of two from 10³ to 10⁶ records. |
| Systems | all six |
| Paper figure | F2 |

**Part 1 — load steps (saturation)**

| Factor | Levels |
|---|---|
| Records | 10⁵ (2 KB) |
| Offered load | 10, 20, 30 … 200 ops/s (steps of 10), Poisson |
| Workload | WO |
| Warm-up / measured per step | 30 s / 180 s |
| Stop rule | after the first step where achieved < 90 % of offered (saturation reached), the remaining steps are skipped |

**Part 2 — data volume**

| Factor | Levels |
|---|---|
| Records | 10³, 10⁴, 10⁶ (10⁵ comes from part 1 at 50 ops/s) |
| Offered load | 50 ops/s |
| Workload, timing | WO, 30 s / 180 s |

Repetitions: 5.

**Procedure**

For each block (system × dataset size), in shuffled order:
1. Reset, then preload the records (section 1.4a).
2. 10⁵ block: for each repetition 1–5, run the load steps one after another until the stop rule, then
   pause 30 s so a saturated system can drain before the next series.
3. 10³, 10⁴, 10⁶ blocks: five 50 ops/s steps (repetitions 1–5), each followed by a 30 s pause.

24 blocks, so 24 preloads.

**Metrics**
* `achieved_ops_s` and `p99_ms` as in 1.8.
* `error_rate` = errors ÷ ops.
* Saturation throughput = the highest achieved rate before the stop rule (taken from the rows during analysis).
* `bottleneck` is left empty, for a note during analysis.

**Output columns (`E2_raw.csv`):** run_id, system, dataset_records, offered_ops_s, rep, achieved_ops_s,
p99_ms, error_rate, bottleneck, notes.

Runs: up to 20 steps + 3 sizes = up to 23 rows per system and repetition, so at most **690 rows**.

---

## 4. E3 — Query expressiveness and cost

| | |
|---|---|
| Question | Which queries can each system answer, are the answers correct, and how long do they take? |
| RQ / contribution | RQ2; C1 |
| Hypothesis H3 | For Q1–Q3, OptimusDB returns complete and correct results faster than client-side evaluation over Gun.js, Autobase, Iroh docs and OpenDHT at 10⁵ and 10⁶ records, and within 25 % of Corrosion; Q4 and Q5 are executed natively only by OptimusDB and Corrosion. |
| Paper figure | F3 |

**Queries**

| Id | Kind | SQL form | Expected rows at 10⁴ / 10⁵ / 10⁶ |
|---|---|---|---|
| Q1 | point lookup | `SELECT * FROM resources WHERE id = 'res-<N/2>'` | 1 / 1 / 1 |
| Q2 | single predicate | `… WHERE status = 'Running'` | 2,512 / 25,024 / 250,048 |
| Q3 | conjunctive range | `… WHERE region = 'eu-west' AND cpu_capacity >= 4 AND memory_capacity >= 8192` | 936 / 9,372 / 93,750 |
| Q4 | aggregation | `SELECT region, COUNT(*), AVG(cpu_capacity) … GROUP BY region` | 4 / 4 / 4 |
| Q5 | two-table join | `SELECT r.id, a.app FROM resources r JOIN allocations a ON a.resource_id = r.id WHERE r.region = 'eu-west'` | 2,500 / 2,500 / 2,500 |

The expected counts are computed exactly from the data generator (`expected_rows` in `bench/workloads.py`).
They were checked against SQLite at 10³ and 10⁴ records.

**Targets (system and query path)**

| Target | How Q1–Q5 are answered |
|---|---|
| OptimusDB, `sqlite` path | SQL through OptimusDB's `sqldml` command. The harness creates tables `resources` and `allocations` in OptimusDB's SQLite store and loads them with multi-row INSERTs through the same command. |
| OptimusDB, `crdt` path | Document query on the CRDT store (criteria query, `LOCAL_THEN_REMOTE_MERGE`). Equality filters run natively; what criteria cannot express (ranges in Q3, GROUP BY in Q4, the join in Q5) is evaluated in the client over the returned documents. |
| Corrosion, `sql` | SQL through `/v1/queries` on its CR-SQLite tables |
| Gun.js, `client_filter` | Q1 by key; Q2–Q5: the wrapper reads every document and filters in the application |
| Autobase + Hyperbee, `range_client_filter` | Q1 by key; Q2–Q5: Hyperbee scan of all entries (none of the queries fixes a key prefix), then filtering in the application |
| Iroh docs, `prefix_client_filter` | Q1 by key; Q2–Q5: all entries are read and filtered in the application |
| OpenDHT, `key_only` | Q1 only (DHT get). Q2–Q5 are recorded as unsupported. |

**Factors:** 7 targets × 5 queries × records 10⁴, 10⁵, 10⁶ (2 KB documents). Repetitions: 10.

**Procedure**

For each block (target × dataset size), in shuffled order:
1. Reset the system.
2. Preload N resource records, then 10,000 allocations: `alloc0` … `alloc9999`, with `resource_id` =
   `res-(i mod N)` and `app` = `app(i mod 50)`. Both are loaded as in section 1.4a.
3. For each repetition 1–10, for each query Q1–Q5: execute it 220 times one after another (closed loop). Discard the first 20;
   record mean and P95 latency of the remaining 200.
4. `correct` = 1 if the query is supported and its last answer has exactly the expected number of rows.

**Output columns (`E3_raw.csv`):** run_id, system, path, query, dataset_records, rep, mean_ms, p95_ms,
rows_returned, rows_expected, correct, notes (`unsupported/failed` when the path cannot run the query).

Rows: 7 × 3 × 5 × 10 = **1,050**, from 21 blocks (21 preloads).

---

## 5. E4 — Edge resource cost

| | |
|---|---|
| Question | What does each system cost in CPU, memory, disk and network on an edge-sized node? |
| RQ / contribution | RQ1; C1 |
| Hypothesis H4 | At 40 ops/s on an edge node, OptimusDB stays below 60 % CPU and 512 MB resident memory per agent. |
| Systems | all six, deployed on the 4 edge hosts only |
| Paper figure | F4 |

**Factors:** offered load 0 (idle), 10, 20, 40 ops/s; workload WO; 2 KB; 10,000 records; 300 s per level
(no warm-up). Repetitions: 5.

**Procedure**

For each system (one block), in shuffled order:
1. Reset on the edge hosts only (`edge-a` … `edge-d`). The smoke test writes on `edge-a` and reads on `edge-d`.
2. Preload 10,000 records through `edge-a` and wait until they are on all 4 edge hosts (section 1.4a). If start or preload fails, write one row with `started_ok` = 0
   per repetition and skip the system.
3. For each repetition 1–5, for each level 0, 10, 20, 40, on the same deployment: drive the load through `edge-a` for 300 s (level 0:
   no load). Meanwhile sample the system's container on all 4 edge hosts once per second through the
   host agents (`docker stats`).

**Metrics (averaged over the 4 edge hosts and the samples)**

| Column | Definition |
|---|---|
| `cpu_pct` | container CPU %. 100 % = one full core; the edge limit is 1 core. |
| `rss_mb` | container memory in MB |
| `disk_mb_per_1k_docs` | data volume size at the end of the level ÷ (documents stored ÷ 1000); documents = 10,000 plus the keys inserted so far (written to `notes`) |
| `net_kb_per_op` | network bytes during the level ÷ operations ÷ 1024 (only for levels with load) |
| `power_w` | empty; there is no power meter in a container testbed |

**Output columns (`E4_raw.csv`):** run_id, system, offered_ops_s, rep, started_ok, cpu_pct, rss_mb,
disk_mb_per_1k_docs, net_kb_per_op, power_w, notes. Rows: 6 × 4 × 5 = **120**.

---

## 6. E5 — Partitions, contention and convergence

| | |
|---|---|
| Question | Does each system keep accepting writes during a network partition, does it lose acknowledged writes, and how fast do replicas agree after healing? |
| RQ / contribution | RQ3; C1 |
| Hypothesis H5 | During a partition OptimusDB accepts writes on both sides; after healing it loses no acknowledged write, its replicas reach identical state, and its convergence time is not longer than the median of the fully replicating baselines (Corrosion, Gun.js, Autobase, Iroh docs). |
| Paper figure | F5 |

**Factors**

| | OptimusDB | Each baseline |
|---|---|---|
| Contention (% of updates on 100 hot keys) | 0, 5, 15, 30, 50 | 0, 30 |
| Partition length | 5, 30, 60, 300 s | 60, 300 s |
| Partition shape | 4 \| 4 and 2 \| 6 | 4 \| 4 |
| Cells | 40 | 4 per baseline (20 in total) |

* **Partition shapes:** 4 | 4 = {cloud-a, cloud-b, fog-a, fog-b} against {edge-a … edge-d}; 2 | 6 = {cloud-a, cloud-b} against the other six.
* Repetitions: 10, so **600 runs** (400 OptimusDB, 200 baselines).

**Procedure**

For each system (one block), in shuffled order: reset on all 8 hosts, preload 10,000 records (2 KB) through
`cloud-a` (section 1.4a), and wait until all 8 replicas are identical. Then, for each run of the block in
shuffled order:

1. Choose 100 hot keys (seeded by the repetition number).
2. **Partition:** add `iptables` DROP rules in both directions between the two groups.
3. For the partition length, run one writer per host. Each writer sends to its own host at 50/8 = 6.25 ops/s
   (50 ops/s in total), Poisson, workload WA (50 % reads, 50 % updates). The given share of updates goes to the
   hot keys, so writers on both sides update the same keys. Every write that returns success is recorded
   with its version number. Version numbers start above those of all earlier runs on the same data.
4. **Heal:** flush the `iptables` rules. Just before healing, record the number of distinct replica states.
5. Poll all replicas every 0.5 s until their content hashes are equal (timeout 600 s).
6. For every acknowledged key, read it on `cloud-a` (a direct read of that key). It counts as lost if it is missing or carries a version
   lower than the highest acknowledged version. A concurrent higher version may legitimately win.

* If the replicas did not converge within 600 s (or the run failed), the system is reset and reloaded before
  the next run, so one bad run cannot leave a broken cluster for the following ones.
* **OptimusDB** replicas are read with `LOCAL_ONLY`, so each host reports its own state.
* **OpenDHT** stores each key on the 8 closest nodes and has no merge, so replica identity and convergence
  are not defined for it. Only availability and loss are measured, after a 20 s settle time.

**Metrics**

| Column | Definition |
|---|---|
| `write_availability_pct` | successful writes ÷ attempted writes during the partition |
| `ack_writes` | keys with at least one acknowledged write |
| `lost_ack_writes` | acknowledged keys whose final state is missing or older (step 8) |
| `divergent_entries` | number of **distinct replica states** at the moment of healing (1 = all identical); the column name is historical |
| `convergence_s` | time from heal to identical replicas (600 if not reached) |
| `replicas_identical` | 1 if identical within 600 s |
| `keys_readable_pct` | 100 × (1 − lost ÷ acknowledged keys) |
| `merge_msgs` | empty (would need gossip-level metrics) |

**Output columns (`E5_raw.csv`):** run_id, system, contention_pct, partition_s, partition_shape, rep,
write_availability_pct, ack_writes, lost_ack_writes, divergent_entries, convergence_s, replicas_identical,
keys_readable_pct, merge_msgs, notes.

---

## 7. E6 — Operational trace replay

| | |
|---|---|
| Question | How does each system behave under a real Swarmchestrate operational workload? |
| RQ / contribution | RQ1, RQ3; all contributions |
| Hypothesis H6 | Under the replayed trace, OptimusDB keeps the P99 end-to-end decision latency below 500 ms and loses no acknowledged write. |
| Requires | `trace\trace.jsonl` (skipped by `run-all` until it exists) |
| Paper figure | F6 |

**Trace format:** one JSON event per line, captured at the OptimusDB agents of the Swarmchestrate demonstrator:

```
{"t": 12.345, "agent": 3, "op": "update",   "key": "res-000000042", "doc": {...}}
{"t": 12.900, "agent": 1, "op": "decision", "key": "res-000000042", "criteria": {...}, "expect": {"status": "Degraded"}}
```

**Factors:**
* all six systems at **4×** replay speed;
* OptimusDB also at **1×**;
* 5 repetitions, so 35 replays.

**Procedure for one replay**
1. Reset on all 8 hosts.
2. Issue each event at time *t* ÷ speed to the host given by `agent` (modulo 8).
3. Writes are recorded as acknowledged when they return success.
4. A `decision` event polls its host every 50 ms with the criteria until the document with that key shows the
   expected values (timeout 30 s).
5. At the end, wait until the replicas are identical (timeout 300 s).

**Metrics**

| Column | Definition |
|---|---|
| `e2e_mean_ms`, `e2e_p99_ms` | time from the acknowledgement of the preceding write of the key to the decision first seeing it |
| `max_staleness_s` | the largest of those times, in seconds |
| `convergence_s` | time to identical replicas after the last event |
| `write_errors`, `writes_total` | failed and attempted writes |
| `notes` | `decisions_timed_out=<n>` |

Rows: 7 cells × 5 = **35**.

---

## 8. Pilot mode

`run-all.ps1 -Pilot` (or `run-experiment.ps1 -Exp <E> -Pilot`) runs a short functional check:

| | Pilot | Campaign |
|---|---|---|
| Repetitions | 1 | per test (10 / 5 / 10 / 5 / 10 / 5) |
| Warm-up / measured (E1) | 30 s / 120 s | 60 s / 300 s |
| E1 cells per system | 5: WA, WB, WC, WO at 2 KB; WO at 8 KB (2 blocks, 12 preloads in total) | 7 |
| Results folder | `results\pilot\` | `results\` |
| Default scenarios of `run-all` | E1 | E1–E5 (+ E6 with a trace) |

The pilot results never count towards the campaign and are not used in the paper. In a pilot of E2–E5 only
the repetitions drop to 1; their step windows, query counts and partition lengths stay as in the campaign.

### Quick mode (`run-all.ps1 -Quick`)

Runs every common scenario E1–E5 once on small data, in about 1.5–2 hours. It is a first look at all
scenarios and an end-to-end check of the whole pipeline. With one repetition it gives no confidence
intervals and no significance tests, so it does not replace the campaign for the paper.

| | Quick | Campaign |
|---|---|---|
| Repetitions | 1 | 10 / 5 / 10 / 5 / 10 |
| Records | 10⁴ (2 KB) everywhere | 10⁵ (E1, E2 steps), 10³–10⁶ (E2, E3), 10⁴ (E4, E5) |
| E1 | WA, WB, WC, WO at 2 KB; 10 s warm-up + 30 s | 7 cells; 60 s + 300 s |
| E2 | 25, 100, 200 ops/s at 10⁴ records; 10 s + 30 s per step | 10–200 ops/s at 10⁵, plus 10³, 10⁴, 10⁶ at 50 ops/s; 30 s + 180 s |
| E3 | 7 targets × Q1–Q5 at 10⁴ records; 2 warm-up + 20 measured queries | 10⁴, 10⁵, 10⁶; 20 + 200 queries |
| E4 | idle and 40 ops/s, 45 s each | 0, 10, 20, 40 ops/s, 300 s each |
| E5 | OptimusDB: contention 0 % and 30 %; each baseline: 30 %; all with a 30 s partition, split 4 \| 4; convergence timeout 120 s | full grid; 600 s timeout |
| Settle wait after preload | up to 120 s | up to 900 s |
| Runs | 24 + 18 + 35 + 12 + 7 = 96 | ~2,900 |
| Results folder | `results\quick\` | `results\` |

**Keeping earlier results.** `run-all.ps1` decides by itself what happens to the results already in the folder of
that mode: if the previous run finished and any of its experiments is requested again, the whole previous run (results
and its logs, plus a copy of the fresh-start log that records the build) is moved to
`results-archive\<its start time>-<mode>\` and a new run starts; if the previous run was interrupted, it is
continued and finished runs are skipped; experiments not yet in the folder are added to it. `-New` forces a new
run, `-Resume` forces continuing. `fresh-start.ps1` also moves all of `results\` to `results-archive\`. Every archived
run stays viewable in the dashboard (Run history page; "Archived …" in the selector).

---

## 9. Statistical analysis

`python -m bench.analyze <E> --metric <column> --group <factor columns…>` (run inside `odb-bench`):

* **Unit of analysis:** one value per run, for example the P99 of that run. Operations are never pooled across runs.
* **Comparisons:** for each condition (combination of the group columns), OptimusDB is compared with each
  baseline. E3 compares paths instead, with the OptimusDB SQLite path as reference.
* **Test:** Welch's t-test if both samples pass Shapiro–Wilk (α = 0.05, n ≥ 3), otherwise Mann–Whitney U (two-sided).
* **Multiple comparisons:** Holm correction over all comparisons of one call. E1 with
  `--group workload doc_size` has 7 conditions × 5 baselines = 35 comparisons.
* **Effect size:** Cliff's δ, magnitude thresholds 0.147 / 0.33 / 0.474 (Romano et al., 2006).
* **Summary per cell** (in the workbook): mean, n, standard deviation, 95 % CI (t-distribution).
* **Outputs:**
  * `results\stats_<E>_<metric>.csv`;
  * `results\cdf_<E>.csv`: latency percentiles (1 … 99.9) per run, from the per-operation files.

**Why 10 repetitions:** with 5 runs per side, the smallest two-sided Mann–Whitney p-value is 0.008. That is
above the Holm threshold for the first of 35 comparisons (0.05 / 35 ≈ 0.0014), so no difference could
ever be declared significant. With 10 runs per side the smallest p-value the harness computes (SciPy's normal approximation) is about 2 × 10⁻⁴, well below that threshold.

---

## 10. Run counts and durations

Durations are estimates for this PC. `progress.ps1` shows the measured time per run once a test is running.

| Test | Runs (rows) | Resets + preloads | Estimated duration |
|---|---|---|---|
| Pilot (E1) | 30 | 12 | 2–3 h |
| E1 | 420 | 24 | ~2 days (420 × 6 min measured + preloads) |
| E2 | ≤ 690 rows | 24 | 1.5–2.5 days (step series; the 10⁶ preloads) |
| E3 | 1,050 rows | 21 (7 of them with 10⁶ records) | 0.5–1.5 days |
| E4 | 120 rows | 6 | ~12 h (120 × 5 min + preloads) |
| E5 | 600 | 6 (+ reloads after non-converged runs) | 1.5–2.5 days |
| E6 | 35 | 35 | depends on the trace (≈ 30 h for a 4-hour trace) |

---

## 11. Known limitations and risks

These are known before the campaign. Check the first ones in the pilot or at the start of each test.

1. **10⁶ records in E2 and E3 (2 KB documents).** That is about 2 GB per replica, and 8 replicas on one disk.
   * OpenDHT keeps its data in memory, and an edge host has 2 GB, so the 10⁶ cells will very likely fail
     for OpenDHT (out of memory). Other systems may come close to their limits too.
   * Failed runs are logged and retried, then reported as "did not start".
   * Watch the first 10⁶ runs. If they fail, decide between: raising the memory limit for those runs,
     capping the volume as for 64 KB, or reporting the failure as a result.
2. **One-way delays.** The Table 7 values are applied per direction (section 1.2). If Table 7 means round-trip
   times, the generator must apply half of each value. Settle this before E1 starts.
3. **OpenDHT has no query operation.** In WO (E1, E2, E4, E6) the 10 % query operations fail for OpenDHT
   and count as errors. Its latency percentiles are over reads, updates and inserts only. Report this next to
   its WO results.
4. **Client-side queries are expensive by design.** For Gun.js, Autobase and Iroh docs, each WO query reads
   the whole dataset through the wrapper. Some of these queries may exceed the 10 s timeout and count as errors.
5. **Gun.js loading and acknowledgements.** The wrapper's bulk load now keeps up to 64 writes in flight
    (each still waits for its acknowledgement). One write at a time took about 120 ms per record, over three
    hours for 10⁵ records; with 64 in flight a 3-node test loaded 20,000 records in 83 s.
    In the first quick run Gun.js on `cloud-a` crashed with "JavaScript heap out of memory" at about 1.5 GB,
    below its 3 GB container limit, because Node.js sets its own heap limit independently of the container.
    The Gun.js and Autobase containers now set the Node.js heap to 85 % of their container limit, and Gun's
    LAN multicast is off (peers are listed explicitly). The calibration then showed that the remaining
    out-of-memory crashes came from the wrapper: each document was a child node, and listing the set
    subscribed to every child (`map().once()`) without releasing the subscriptions, so the heap grew by about
    2 MB per 1,000 documents on every scan (WO issues 5 scans/s). Documents are now stored as properties of
    one set node (same per-document last-writer-wins merge); a scan is one read of that node, and the heap
    stays flat (tested: 12 scans of 5,000 documents, 32 MB before and after; replication, updates and
    queries checked between two peers). `GUN_SCHEMA=nodes` restores the old schema.
    Separately: In the earlier emulation, some Gun.js writes under concurrency never received
   an acknowledgement within 10 s. They are counted as errors. Check the pilot's `errors` column for Gun.js.
6. **Single machine.** All hosts share one CPU and one disk, and the limits are cgroup shares, not separate
   devices. E4 measures edge-sized containers, not Raspberry Pi 4 boards, and has no power measurement.
7. **E2 and E4 levels share a deployment.** Load steps (E2) and load levels (E4) run on the same data, one
   after another, without a reset in between.
8. **E5 `divergent_entries`** counts distinct replica states, not divergent keys (section 6).
9. **E6 needs the trace.** Without `trace\trace.jsonl` it does not run.
10. **Iroh docs replication.** In the first pilot, Iroh stopped accepting writes (and reads) after about 25,000
    records while the link profiles were active, with all nodes idle. The preload now runs without link
    emulation (section 1.4a). In the second pilot it loaded 10⁵ records in about 2 minutes, but the sample
    was still not readable on every host after 900 s. In a 3-node test outside the testbed it replicated
    within seconds. When the wait times out, the log now lists how many sample keys each host has. If Iroh also stalls under the measured load, its runs fail with
    timeouts. `GET /health` on port 7006 tells whether the wrapper is alive while the store is blocked, and
    `RUST_LOG=iroh_docs=debug` in its container shows where it waits.

---

## 12. What Section 8 of the paper must state

* OptimusDB is built, unmodified by the testbed, from the commit of the OptimusDB repository named in
  `versions.env` (cite that full commit hash). From that commit on, documents are written in batches with
  `PutAll` (one oplog entry per batch of up to 500 documents / 512 KiB), using a vendored go-orbit-db v1.21.0
  (`third_party/go-orbit-db`) whose document index has the PUTALL bug fixed and is updated incrementally.
  Reads and updates by `_id` read one index entry instead of scanning the store; a query writes back only
  rows learned from peers that are missing locally; `LOCAL_THEN_REMOTE_MERGE` asks peers only when the local
  replica has no matching rows (`PARALLEL_MERGE` always asks both).
  API commands are handled concurrently (up to `SERVICE_CONCURRENCY`, default 32); earlier builds handled one
  command at a time, and the HTTP API dropped the request's query options.
  Log lines are persisted to SQLite by a background writer in batches (earlier: one synchronous insert per line
  under a global lock); an update is one write of the document (earlier: delete + insert), and lineage/metadata
  bookkeeping runs after the acknowledgement, through one queue that keeps the latest state per document.
  Concurrent single-document writes to a store are combined into one oplog entry (group commit; a write to an
  idle store is written at once). The document index applies a local write's entry directly instead of walking
  the whole log on every write. Equality conditions on `type`, `status`, `region` and `resource_id` use field
  indexes, and decoded documents are cached (up to 128 MiB per store, tied to the stored bytes; readers get copies). An SQL
  result is deduplicated only when rows from peers were merged into it.
* OptimusDB runtime settings in the benchmark (logged per run in `runtime-settings.json`): log level WARN;
  `GOMAXPROCS` = the container's CPU limit rounded up and `GOMEMLIMIT` = 80 % of its memory limit (the Go 1.19
  build does not read cgroup limits, whereas the Rust and Node.js runtimes of the baselines do); `GOGC=200`;
  OptimusDB's internal metrics sampling off; IPFS node key Ed25519 instead of RSA-2048 (kubo's own default
  since v0.13; every GossipSub message is signed with it) and no DHT announcement of each written block
  (agents are connected directly and fetch blocks over bitswap). Both IPFS settings were chosen from a CPU and
  lock profile of the write path (`profile-optimusdb.ps1`): RSA signing and DHT traffic were the largest items.
* Durability: Corrosion runs SQLite in WAL mode with `synchronous = NORMAL` (`corro-types/src/sqlite.rs` at the
  pinned commit): commits are not flushed to disk one by one. OptimusDB runs with the equivalent setting
  (`OPTIMUSDB_IPFS_SYNC=false`: IPFS blocks and the store-head cache are written without an fsync per write;
  files are written atomically, so a power loss can lose the last writes but not corrupt the store). The
  other baselines run with their defaults.
* Indexes: OptimusDB indexes `type`, `status`, `region` and `resource_id` by default; Corrosion's schema and
  OptimusDB's SQLite tables get the same secondary indexes (`status`, `region`, `allocations.resource_id`),
  so no system has an index advantage in E3.
* OptimusDB local query results are sent as the stored JSON documents (no decode and re-encode) when they are
  returned unchanged (no annotations, local rows). When a query is only string equalities on indexed top-level
  fields (the WO matchmaking query), the field indexes select the documents exactly and none is decoded.
* Same result on every system (fixed after quick run 3, before the pilot): every operation returns the whole
  documents and the client decodes them. Until then Corrosion's WO query fetched only the ids of the matching
  rows (about 640 short strings at 10⁴ records) while every other system returned the matching documents
  (about 640 × 2 KB), which favoured Corrosion in E1 (WO), E2 and E4. Reads on the wrapper-based systems
  (Gun.js, Autobase, Iroh) now also decode the returned document, as OptimusDB's and Corrosion's already did.
  Quick-run results before this fix are not comparable for Corrosion's WO figures. Corrosion's answer (NDJSON events
  whose document column is a JSON string) is decoded in one call per response, and an error event counts as an error.
* Load generator validity (added after quick run 4, before the pilot): the client is one Python process. Every
  load-driven run (E1, E2) records the generator's CPU (% of one core), the delay between each operation's
  scheduled and actual issue time (median and P99), and the target node's peak CPU against its limit. A run is
  marked `client_limited` when the node's CPU was below 85 % of its limit and the generator used ≥ 85 % of a core,
  or issued operations a median > 10 ms late in a run without failures (in a failing run a late issue alone is not
  enough: the backlog of a failing system also slows the client; quick run 5 showed this with OpenDHT); `node_cpu_bound` when the node's CPU reached 85 % of its
  limit. E2's `bottleneck` column says which. An E2 step that fails while client-limited is not counted against
  the system: its saturation is reported as a lower bound (the last step it passed). In quick run 4 both
  OptimusDB and Corrosion failed the 200 ops/s step while operations were issued a median 35–43 ms late
  (about 1 ms in every other run), so that step measured the client; it is not used.
* OptimusDB query path (same results, measured before the pilot): equality conditions on indexed fields are
  intersected before any document is read; cached documents are filtered without copying; the existence check
  for rows learned from peers no longer reads every local row; the HTTP response is encoded once (it was
  encoded twice). Metadata enrichment, the semantic index and Loki shipping are off
  (no baseline has an equivalent). Corrosion logs at `warn`; Iroh's wrapper logs at `warn`; OpenDHT runs without
  verbose logging.

* Evaluation report: every run's results are also rendered as a paginated report (dashboard page *Evaluation report*;
  a self-contained copy is saved in the run's results folder when the run finishes). Its figures, tables, verdicts and
  generated sentences come from the result files only; interpretation appears only in the run's analyst notes file.

* Changes after the first E1 pilot at 10⁵ records (17 Oct 2026), before the campaign. The pilot's results are not
  used in the paper; these changes apply to every system alike and are fixed before any campaign run.
  * **Load generator: several processes.** At 10⁵ records the WO query returns about 6,250 documents
    (12.5 MB at 2 KB, 50 MB at 8 KB), five times a second, and the single Python process spent most of its core
    decoding them: in the pilot the generator used 65 % (OptimusDB) and 84 % (Corrosion) of a core at 2 KB and
    99 % at 8 KB, and simple reads queued behind the decoding (Corrosion's read median 48 ms in WO against 2.6 ms
    in WB). Timed runs now deal the same schedule round-robin to `client_workers` processes (default 4, in
    `testbed.yaml` under `run:`), each with its own event loop and connections. Operation *i* of the schedule
    goes to worker *i* mod 4; every worker rebuilds the whole sequence from the same seeds, so the operations, their
    keys, documents and scheduled times are identical to the single-process generator (checked by a test). All
    workers use the system-wide monotonic clock, so latency is still measured from the scheduled time. The
    client-limited rule applies to the busiest worker (≥ 85 % of a core); `workers=` is recorded in each run's
    notes. Local check (fake store returning 6,250 documents per query, WO at 50 ops/s): read median 44.5 ms with
    one process, 3.4 ms with four; busiest worker 10 % CPU. E5's acknowledging writers and E6's trace replay keep
    one process.
  * **Fresh connections after a redeployment.** Requests cancelled at the 10 s timeout while a node hung left the
    client's connection pool exhausted; every later request of the block then failed with `PoolTimeout` (pilot:
    Autobase WA and WO 2 KB never started). The client is now renewed after every reset.
  * **Wrapper scans (Gun.js, Autobase, Iroh docs).** These systems have no query language and evaluate WO
    queries in the wrapper by reading every document (caveat 4). The evaluation is unchanged (same documents,
    exact field-by-field check), but it no longer holds every document in memory at once:
    * Gun.js reads and scans its own replica (`gun._.graph`) instead of `once()`, which also asked all 7 peers
      for the whole set node (~200 MB at 10⁵) on every query; documents whose stored JSON text lacks a
      criterion (`"region":"eu-west"`) are not parsed. Local check (2 peers, 2 × 10⁴ records, 5 queries/s):
      median 3.8 s and memory growing to 2 GB in 30 s before; 96 ms and flat memory after, same rows. At
      10⁵ records one scan takes about 330 ms and memory stays at about 1.2 GB; every peer held all 10⁵
      documents in its own replica. `GUN_READ=network` restores the old reads.
    * Autobase filters while it streams the Hyperbee view instead of collecting all values first.
    * Iroh docs reads contents 64 at a time and parses only candidate documents (single query at 10⁵ records:
      9.4–10.2 s before, 2.9–3.2 s after, same 6,256 rows).
    * Gun.js and Autobase run at most 2 scans at a time (others wait; the wait is part of their latency) and do
      not start a scan whose client has already left. Without this, scans arriving faster than they finished
      piled up until the heap ran out (local Autobase check, 2 nodes, 10⁵ records, WO at 50 ops/s: heap limit
      within a minute; with the limit the node stays up, reads, updates and inserts are answered, P99 0.2–0.5 s).
  * What remains is each system's own behaviour, reported as such: a full Autobase scan of 10⁵ documents took
    7.6–17.6 s in the local check (above the 10 s operation timeout), so its WO queries time out; a Gun.js scan takes about 0.3 s and an Iroh scan about 3 s, so at 5 queries/s
    their scans queue and some time out (local checks on 2 CPUs; the testbed gives each node 1–1.5 CPUs). Autobase's resident memory at 10⁵ × 2 KB was 1.1–1.9 GB per node
    (JavaScript heap 0.35–0.65 GB; the rest is native storage memory), close to the edge hosts' 2 GB limit,
    which is where the pilot's edge nodes stopped. Iroh docs: in iroh-docs 0.101 a content download that fails is
    retried only when a neighbour announces that content again (`engine/live.rs`, `missing_hashes`), so after a
    large preload some entries stay without content (pilot: 185–200 of 200 sample keys readable per host after
    900 s). This is the library's behaviour; it is reported, not worked around.
  * H1 comparison detail: the verdict follows the registered rule unchanged (best baseline by P99). When that
    baseline failed more than 1 % of its WO operations or could not run some of them (Iroh's queries timed out
    in the pilot; OpenDHT has no query), its P99 covers only the operations it completed, so the dashboard and
    report also state this and give the comparison with the best baseline that completed the whole mix. Whether
    the paper's H1 uses that comparison instead must be decided before the campaign and written here; until then
    it is information only.
  * OptimusDB is pinned in `versions.env` to commit `479504d`, the build of quick run 6 and the pilot.
  * **OptimusDB reads by id (after quick run 7, before the campaign).** In quick run 7 Q1 (one document by id)
    took 1.21 ms on OptimusDB against 0.94 ms (Iroh docs) and 1.19 ms (Gun.js). Against a stand-in server that
    answers every system instantly, the harness's OptimusDB read cost 0.13–0.16 ms more than a wrapper read:
    the read was a POST of a JSON command, the wrappers' a plain GET. OptimusDB now has
    `GET /<context>/doc/<id>?dstype=&strategy=` (commit after `479504d`): the same answer as the query command
    with criteria `[{"_id": id}]`, served from the local replica in the HTTP handler when the document is there
    and the strategy returns local rows, otherwise through the query command. Per-request log messages are now
    level-checked instead of sent through a channel. The OptimusDB adapter uses the endpoint for every read in
    every experiment (E1, E2, E4 and E3 Q1), and falls back to the query command on builds without it. Local
    measurement of the client side: 1.010 → 0.880 ms against 0.863 ms for a wrapper read. Server-side dispatch
    saved about 0.02 ms in a model of the request path. H3 is unchanged.
  * `run-all.ps1 -Workloads WO` (E1 only) runs just the WO cells, for checking the load generator:
    `.\run-all.ps1 -Pilot -Workloads WO -Systems optimusdb,corrosion`.

* Results at a glance (dashboard, report and paper export): one figure per run with a radar of seven measures and
  the measured values. Each axis runs from the worst to the best value measured on it (log scale); it shows each
  system's position per measure and is not a weighted or combined score. The hypotheses are decided only by
  their registered rules.

* The testbed is emulated on a single host: 8 hosts as containers with cgroup CPU and memory limits, links
  emulated with `tc netem` (one-way values), partitions with `iptables`.
* Each system is deployed and loaded once per block (system × dataset) and all runs of the block follow on that
  data in random order (YCSB load and run phases); blocks are shuffled.
* Datasets are preloaded without link emulation, and each measured window starts only once a sample of
  the data is readable on every host; the link profiles are active during warm-up and measurement.
* The 64 KB series of E1 uses 1.25 × 10⁴ records, keeping the data volume per replica at about 800 MB,
  equal to the 8 KB series.
* OptimusDB's SQLite path in E3 is loaded through its `sqldml` interface into tables created for the
  benchmark. Its CRDT path uses the document query with its own operators for equality and ranges (Q3:
  `$gte`), and client-side evaluation of aggregation and joins (Q4, Q5). Systems without a query language
  (Gun.js, Autobase, Iroh, OpenDHT) filter in the client.
* OptimusDB's per-row provenance annotations (`_source`, `_trace`; a diagnostic option on by default) are
  turned off in all experiments, since no baseline returns comparable fields.
* Baseline validity: before the campaign, every baseline that fails or saturates at low load is calibrated
  (`calibrate-baselines.ps1`: WA at rising rates on a single node and on the 8-host cluster, with CPU and
  memory). A failure counts as the system's behaviour only if it is CPU-bound under the testbed limits or
  appears with replication only; a failure on an unsaturated single node is a benchmark defect and is fixed
  first. The calibration reports are archived with the results.
* In E1, a run with more than 20 % errors (or a node that stopped answering) is followed by a fresh deployment
  and reload before the next run of the block, so a saturated run cannot leave a backlog that distorts the next
  one (observed with Gun.js: WA failed only after WO had saturated it).
* Autobase indexers: all 8 nodes are writers; the first 3 (cloud-a, cloud-b, fog-a) are indexers.
  Calibration (WA and WO, 5-50 ops/s, cluster with link profiles): with all 8 as indexers, 13-27 % of
  operations timed out from 10 ops/s and memory grew to about 780 MB; with 3 indexers, no errors up to 50 ops/s.
  Each baseline runs in the configuration that serves it best; `autobase_indexers` (testbed overrides)
  changes it, and the value used is recorded in `runtime-settings.json`.
* Autobase wrapper: reads and queries use the local Hyperbee view, which a background loop brings up to date
  every 100 ms (as in the other systems, reads do not force a sync with all peers); replica comparison forces
  an update. Both Node.js wrappers log a failed request instead of exiting.
* E2 saturation: the highest offered load at which a system achieves ≥ 90 % of the offered operations it
  supports, with < 1 % errors (OpenDHT's WO queries are unsupported, so its target is 90 % of the rest). A system
  that does not keep up even at the lowest offered load counts as 0 ops/s in the baselines' median (H2) rather
  than being left out. This rule was fixed before the campaign.
* OpenDHT supports Q1 only, and its WO results exclude query operations (reported as unsupported, not as
  errors); 64 KB documents exceed its 64 KiB value limit.
* E4 reports container resource use on edge-sized containers (1 CPU, 2 GB), not measurements on Raspberry
  Pi hardware, and no power figures.
* Statistics: run-level values; Welch or Mann–Whitney with Holm correction; Cliff's δ; 95 % CIs.
