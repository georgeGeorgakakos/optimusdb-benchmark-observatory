# optimusdb-bench

Harness for the OptimusDB journal evaluation (Section 8 of the paper). It produces the evidence that
fills `OptimusDB_Section8_Evidence.xlsx`. **Nothing in this repository is a result.**
Results exist only after you run the experiments on the real testbed.

```
bench/spec.py        single source of truth: systems, experiments E1–E11, factors, raw columns, hypotheses
bench/workloads.py   YCSB-style mixes (WA/WB/WC/WO), scrambled Zipfian keys, 256 B–64 KB docs
bench/loadgen.py     open-loop generator (latency from scheduled start → no coordinated omission)
bench/adapters.py    OptimusDB, Corrosion and OpenDHT natively; Gun.js, Autobase + Hyperbee and Iroh docs via wrappers/
bench/faults.py      tc netem per tier pair, iptables partitions, crash/restart, churn
bench/observe.py     /proc resource sampling, convergence (state-hash equality), ack-write loss, election snapshots
bench/runner.py      E1–E5, E7–E9 orchestration, E3 client-side query evaluation, E11 scoring → results/<E>_raw.csv
bench/trace.py       E6 trace replay
bench/analyze.py     Shapiro–Wilk → Welch / Mann–Whitney, Cliff's δ, Holm; CDF tables
wrappers/            gun_http.mjs, autobase_http.mjs (Node.js) and iroh_http (Rust) — same HTTP contract
tools/build_workbook.py   regenerates the Excel workbook from spec.py
tools/build_drawio.py     regenerates the testbed diagram
tests/               pipeline tests with in-memory and mocked adapters (validate the harness only)
```

## Systems under test (decentralized data stores only)

| id | System | Access | Notes |
|---|---|---|---|
| optimusdb | OptimusDB | native HTTP command API | preferred-coordinator option disabled |
| corrosion | Corrosion (superfly, main @ ef243dd) | native HTTP API | schema: `resources` and `allocations` tables |
| gun | Gun.js 0.2020.1239 | `wrappers/gun_http.mjs` | full-mesh peer list, radisk |
| autobase | Autobase 7.28.2 + Hyperbee view | `wrappers/autobase_http.mjs` | every node is writer and indexer |
| iroh | iroh-docs 0.101 | `wrappers/iroh_http` (Rust) | persistent store, shared namespace via ticket |
| opendht | OpenDHT 4.4.1 | REST proxy of `dhtnode` | in-memory, k = 8 replicas, permanent puts |

OrbitDB and go-orbit-db are not baselines: OptimusDB is built on them. Distributed (Raft/cluster) and
blockchain-based systems are compared qualitatively in Section 2 only.

## 0. Before any run (blocking items)

1. **Disable the preferred-coordinator option** in `election/reputationBasedElection.go`
   (`selectCandidate` votes for `optimusdb1` whenever its score > 10). Add an env switch
   `ELECTION_POLICY=reputation|random|lowest_id|argmax` so E9 can compare policies.
2. **Merge the agent-side credential verifier** (challenge endpoint + the six checks of
   Section 6) before E10. Without it E10 cannot run and contribution C4 must be narrowed.
3. **Capture the trace for E6**: log every API call at the demonstrator's agents for ≥ 4 h
   (format in `bench/trace.py`).
4. **Annotate the E11 corpus**: two annotators, adjudication, held-out test split that was
   never used for prompt design or fine-tuning; record agreement in `E11_agreement_raw`.
5. **E3 allocations table**: Corrosion gets it from its schema file; for OptimusDB create the
   `allocations` table on the SQL path before E3 (Q5 joins it). Systems without SQL store
   allocations as documents and join on the client.
6. Pin versions of all systems in the `Baselines` sheet and the commit of OptimusDB in `Run_log`.
7. Synchronise clocks (chrony) on all hosts; staleness metrics depend on it.

## 1. Setup

```bash
pip install httpx pyyaml numpy scipy pandas pytest
# per node, next to the OptimusDB agent:
#   corrosion agent (superfly/corrosion)                 -> :8080
#   node wrappers/gun_http.mjs                           -> :7004   (npm i gun express)
#   node wrappers/autobase_http.mjs                      -> :7005   (npm i autobase@7.28.2 corestore hyperbee hyperswarm express)
#   wrappers/iroh_http (cargo build --release)           -> :7006
#   dhtnode -b <bootstrap> --proxyserver 8000            -> :8000
cp config/testbed.example.yaml config/testbed.yaml   # fill in endpoints, nodes, reset hooks
python -m pytest -q tests                            # harness self-test (no cluster)
```

* **Autobase**: start the first node without `BOOTSTRAP`, read its base key from `GET /admin/key`,
  start the others with `BOOTSTRAP=<key>`, then call `POST /admin/add-writer {key}` on the first node
  for every other node's writer key. Peer connectivity uses Hyperswarm by default (`DHT_BOOTSTRAP`
  for a private DHT); on testbeds without UDP hole punching use `REPL_PORT` and `PEERS=host:port,...`
  for direct TCP replication streams (same Corestore protocol).
* **Iroh docs**: start the first node without `TICKET`, read `GET /ticket`, start the others with
  `TICKET=<ticket>`. The endpoint uses the minimal preset (no public relays or discovery).
* Both wrappers were smoke-tested with two local nodes (writes on either node replicate to the other).

The load generator must run on its own host (never on an agent).

## 2. Running

| Exp | Command | Notes |
|---|---|---|
| E1 | `python -m bench.runner E1` | 6 systems × (4 workloads at 2 KB + WO at 3 sizes) × 10 reps |
| E2 | `python -m bench.runner E2` | stops stepping a system one level after saturation |
| E3 | `python -m bench.runner E3` | SQL paths for OptimusDB/Corrosion; client-side evaluation otherwise; OpenDHT Q2–Q5 recorded as unsupported |
| E4 | `python -m bench.runner E4` (Raspberry Pi cluster) | all six systems |
| E5 | `python -m bench.runner E5` | OptimusDB full grid; baselines 4\|4 × {0, 30}% × {60, 300} s |
| E6 | `python -m bench.trace --trace trace.jsonl --system <id> --speed 4` (OptimusDB also `--speed 1`) | 5 replays per cell |
| E7 | `python -m bench.runner E7` | OptimusDB strategies × initiator tier × time budget |
| E8 | `python -m bench.runner E8` | 4–64 agents, weak and strong scaling |
| E9 | `python -m bench.runner E9` (prompts to switch election policy) | 50 trials per cell |
| E10 | after step 0.2: WO with the credential provider, AC on/off, plus each denial cause | |
| E11 | run TinyLlama and the rule-based extractor over the test split, then `python -m bench.runner E11 --gold gold.jsonl --pred pred.jsonl --extractor tinyllama` | |

Runs are resumable: a `run_id` already in `results/<E>_raw.csv` is skipped. Cells are executed
in a randomised, interleaved order so cloud noise is spread across systems.

## 3. From CSV to paper

1. Paste `results/<E>_raw.csv` rows into sheet `<E>_raw` from row 5; summaries and charts update.
2. `python -m bench.analyze E1 --metric p99_ms --group workload` → paste `results/stats_E1_p99_ms.csv` into `Stats`.
3. Fill the [TO RUN] tables and sentences in Section 8 only from these sheets.
4. Archive `results/`, the workbook, configs and this repository with a DOI (principle P4).

## Notes on fairness

* Every system gets the same hardware, netem profiles, data, workload generator and client host,
  and runs with its documented defaults. A system that does not start on a 4 GB Raspberry Pi records
  `started_ok = 0` with the error rather than being tuned more than the others.
* Wrappers map each benchmark operation to one native call and add no caching or batching.
* Systems without a query language filter on the client (over a native range/prefix scan where one
  exists), as an application would. OpenDHT cannot enumerate keys, so its WO scans are recorded as
  unsupported operations and its snapshots read the keys the harness wrote.
* Merge semantics differ: OptimusDB, Corrosion, Gun.js and Iroh docs resolve concurrent writes by
  last-writer-wins; Autobase applies its deterministic causal order (a concurrent update can be
  linearized before an earlier-acknowledged one); OpenDHT keeps all values and the adapter reads the
  highest (version, writer_ts). Superseded writes under these rules are not counted as lost.

## Docker Desktop multi-host deployment

When `testbed.yaml` has a `cluster:` section (generated by `optimusdb-deploy/gen-config`), the harness drives
the hosts through their control agents instead of SSH:

* `bench/cluster.py`: start/stop/wipe, per-system cluster join, smoke test, netem, mesh check
  (`python -m bench.cluster --help`);
* `runner.cfg_reset` calls `cluster.reset` before every run, so only the system under test runs and
  starts from empty data;
* `faults.Node` with `agent_url` runs tc/iptables in the host's network namespace (interface `wg0`);
  `observe.sample_container` reads `docker stats` through the agent for E4.

Failed runs are written to `results/failures.log` and retried when the same experiment is started again.
