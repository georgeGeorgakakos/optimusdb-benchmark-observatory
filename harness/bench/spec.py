"""Single source of truth for the OptimusDB evaluation (Section 8 of the paper).

The Excel workbook builder, the harness CSV exporters and the paper text all read
these definitions, so experiment IDs, factor levels and column names stay identical
across the three artefacts.
"""

SYSTEMS = [
    # id, label, replication / merge mechanism, data model / query interface, version, deployment notes — all decentralized (P2P class of Table 1)
    ("optimusdb", "OptimusDB", "Merkle-CRDT over IPFS; GossipSub", "Documents, key-value, event log; SQL and CRUD (this work)", "commit <hash>", "Go agent, go-orbit-db v1.21, Kubo v0.19, libp2p v0.27; preferred-coordinator option DISABLED"),
    ("corrosion", "Corrosion", "CR-SQLite CRRs (per-column LWW); SWIM gossip over QUIC", "SQLite tables; SQL over HTTP", "main @ ef243dd", "One corrosion agent per node, native HTTP API (/v1/transactions, /v1/queries); default gossip settings"),
    ("gun", "Gun.js", "HAM (per-key LWW); DAM mesh", "Graph; graph API via wrapper", "0.2020.1239", "Node.js peer per node, full-mesh peer list, radisk persistence, wrappers/gun_http.mjs"),
    ("autobase", "Autobase + Hyperbee", "Causal linearization of Hypercore logs; Hyperswarm", "Multi-writer log with Hyperbee view; key and range reads via wrapper", "7.28.2", "Node.js, one writer core per node added as writer and indexer, wrappers/autobase_http.mjs"),
    ("iroh", "Iroh docs", "Range-based set reconciliation; per-author LWW; QUIC", "Signed key-value entries; key and prefix reads via wrapper", "0.101.0", "Rust wrapper (wrappers/iroh_http) with persistent store, one author per node, shared namespace"),
    ("opendht", "OpenDHT", "Kademlia DHT; k = 8 closest nodes; no merge", "Key -> set of values; get/put via REST proxy", "4.4.1", "dhtnode per node with proxy server; permanent puts; updates as values with increasing seq"),
]

TIERS = ["cloud", "fog", "edge"]

WORKLOADS = [
    # id, read %, update %, insert %, scan/query %, key distribution, description
    ("WA", 50, 50, 0, 0, "zipfian(0.99)", "YCSB-A update-heavy"),
    ("WB", 95, 5, 0, 0, "zipfian(0.99)", "YCSB-B read-mostly"),
    ("WC", 100, 0, 0, 0, "zipfian(0.99)", "YCSB-C read-only"),
    ("WO", 60, 20, 10, 10, "zipfian(0.99)", "Orchestration mix: status reads, status updates, new descriptors, matchmaking queries"),
]

DOC_SIZES = ["256B", "2KB", "8KB", "64KB"]
DATASET_SIZES = [1_000, 10_000, 100_000, 1_000_000]

QUERIES = [
    ("Q1", "Point lookup by key", "SELECT * FROM resources WHERE id = ?"),
    ("Q2", "Single-predicate filter", "SELECT * FROM resources WHERE status = 'Running'"),
    ("Q3", "Conjunctive range filter", "SELECT * FROM resources WHERE region = ? AND cpu_capacity >= 4 AND memory_capacity >= 8192"),
    ("Q4", "Aggregation", "SELECT region, COUNT(*), AVG(cpu_capacity) FROM resources GROUP BY region"),
    ("Q5", "Two-table join", "SELECT r.id, a.app FROM resources r JOIN allocations a ON a.resource_id = r.id WHERE r.region = ?"),
]

STRATEGIES = ["LOCAL_ONLY", "QUORUM_2", "QUORUM_4", "LOCAL_THEN_REMOTE_MERGE", "PARALLEL_MERGE", "REMOTE_ONLY"]
ELECTION_POLICIES = ["reputation", "random", "lowest_id", "argmax"]
FAILURE_SCENARIOS = ["follower_crash", "coordinator_crash", "partition_coord_minority", "partition_coord_majority"]
AC_OUTCOMES = ["granted", "denied_presentation_sig", "denied_replay", "denied_untrusted_issuer",
               "denied_expired_or_revoked", "denied_capability"]
AI_FIELDS = ["resource_type", "deployment_tier", "dependencies", "sla_parameters", "geo_region"]

# ---------------------------------------------------------------------------
# Experiments. 'raw' lists the per-run columns the harness writes (one row per
# run = one repetition of one factor combination); the workbook sheet <id>_raw
# has exactly these columns.
# ---------------------------------------------------------------------------
EXPERIMENTS = [
    # Part A (Section 8.4): comparative, all six systems.  Part B (Section 8.5): OptimusDB mechanisms vs ideal or ablations.
    dict(id="E1", part="A", section="8.4", title="Latency and tail behaviour",
         rq="RQ2", contrib="C1, C3",
         factors="system (6) × workload WA/WB/WC/WO; 2 KB; 10^5 records; 50 ops/s open loop; WO also with 256 B, 8 KB, 64 KB (dataset volume capped at 10^5 × 8 KB ≈ 800 MB, so 64 KB uses 12,500 records)",
         reps=10, duration="300 s measured after 60 s warm-up",
         hypothesis="H1: for WO, OptimusDB's P99 latency is within 25% of the best baseline, and its tail ratio P99.9/P50 is not larger than the median of the baselines.",
         raw=["run_id", "system", "workload", "doc_size", "rep", "ops", "errors", "mean_ms", "p50_ms", "p95_ms", "p99_ms", "p999_ms", "achieved_ops_s", "start_utc", "notes"],
         figure="F1"),
    dict(id="E2", part="A", section="8.4", title="Throughput and data volume",
         rq="RQ2", contrib="C1",
         factors="system (6) × offered load 10-200 ops/s (step 10) at 10^5 records; and data volume 10^3-10^6 records at 50 ops/s; workload WO",
         reps=5, duration="180 s per step after 30 s warm-up",
         hypothesis="H2: OptimusDB's saturation throughput is at least the median of the baselines, and its P99 at 50 ops/s grows by less than a factor of two from 10^3 to 10^6 records.",
         raw=["run_id", "system", "dataset_records", "offered_ops_s", "rep", "achieved_ops_s", "p99_ms", "error_rate", "bottleneck", "notes"],
         figure="F2"),
    dict(id="E3", part="A", section="8.4", title="Query expressiveness and cost",
         rq="RQ2", contrib="C1",
         factors="OptimusDB (CRDT path, SQLite path), Corrosion (SQL), Gun.js (client), Autobase/Hyperbee (range + client), Iroh docs (prefix + client), OpenDHT (key only) × Q1-Q5 × 10^4/10^5/10^6 records",
         reps=10, duration="200 queries per cell after 20 warm-up queries",
         hypothesis="H3: for Q1-Q3, OptimusDB returns complete and correct results faster than client-side evaluation over Gun.js, Autobase, Iroh docs and OpenDHT at 10^5 and 10^6 records, and within 25% of Corrosion; Q4 and Q5 are executed natively only by OptimusDB and Corrosion.",
         raw=["run_id", "system", "path", "query", "dataset_records", "rep", "mean_ms", "p95_ms", "rows_returned", "rows_expected", "correct", "notes"],
         figure="F3"),
    dict(id="E4", part="A", section="8.4", title="Edge resource cost",
         rq="RQ1", contrib="C1",
         factors="system (6) × offered load 0/10/20/40 ops/s on the four Raspberry Pi 4 edge devices; workload WO; 2 KB",
         reps=5, duration="300 s per level",
         hypothesis="H4: at 40 ops/s on a Raspberry Pi 4, OptimusDB stays below 60% CPU and 512 MB resident memory per agent.",
         raw=["run_id", "system", "offered_ops_s", "rep", "started_ok", "cpu_pct", "rss_mb", "disk_mb_per_1k_docs", "net_kb_per_op", "power_w", "notes"],
         figure="F4"),
    dict(id="E5", part="A", section="8.4", title="Partitions, contention and convergence",
         rq="RQ3", contrib="C1",
         factors="OptimusDB: contention 0/5/15/30/50% of writes on 100 hot keys × partition 5/30/60/300 s × split 4|4 and 2|6; baselines: split 4|4 × contention 0/30% × partition 60/300 s",
         reps=10, duration="partition + up to 600 s",
         hypothesis="H5: during a partition OptimusDB accepts writes on both sides; after healing it loses no acknowledged write, its replicas reach identical state, and its convergence time is not longer than the median of the fully replicating baselines (Corrosion, Gun.js, Autobase, Iroh docs).",
         raw=["run_id", "system", "contention_pct", "partition_s", "partition_shape", "rep", "write_availability_pct", "ack_writes", "lost_ack_writes", "divergent_entries", "convergence_s", "replicas_identical", "keys_readable_pct", "merge_msgs", "notes"],
         figure="F5"),
    dict(id="E6", part="A", section="8.4", title="Operational trace replay",
         rq="RQ1, RQ3", contrib="All",
         factors="system (6) at 4× replay speed of a captured Swarmchestrate trace (>= 4 h); OptimusDB also at 1×",
         reps=5, duration="full trace",
         hypothesis="H6: under the replayed trace, OptimusDB keeps the P99 end-to-end decision latency below 500 ms and loses no acknowledged write.",
         raw=["run_id", "system", "speed", "rep", "e2e_mean_ms", "e2e_p99_ms", "max_staleness_s", "convergence_s", "write_errors", "writes_total", "notes"],
         figure="F6"),
    dict(id="E7", part="B", section="8.5", title="Query strategies",
         rq="RQ2", contrib="C3",
         factors="strategy (6) × initiator tier (3) × time budget 300/1200/3000 ms; 8 agents; 10^5 records; Q3 with WO background at 20 ops/s",
         reps=10, duration="500 queries per cell",
         hypothesis="H7: LOCAL_ONLY has the lowest latency; QUORUM_2, QUORUM_4, LOCAL_THEN_REMOTE_MERGE and PARALLEL_MERGE trade latency for completeness along a monotone frontier; from an edge initiator LOCAL_THEN_REMOTE_MERGE reaches >= 95% completeness within a 1.2 s budget.",
         raw=["run_id", "strategy", "initiator_tier", "time_budget_ms", "rep", "mean_ms", "p99_ms", "completeness_pct", "staleness_s", "notes"],
         figure="F7"),
    dict(id="E8", part="B", section="8.5", title="Scalability in the number of agents",
         rq="RQ1", contrib="C1",
         factors="agents 4/8/16/32/64 × weak scaling (10 ops/s per agent) and strong scaling (fixed 80 ops/s); workload WO",
         reps=5, duration="300 s",
         hypothesis="H8: weak-scaling efficiency stays >= 80% up to 32 agents; per-agent GossipSub traffic grows sub-linearly.",
         raw=["run_id", "agents", "scaling", "rep", "offered_ops_s", "achieved_ops_s", "mean_ms", "p99_ms", "convergence_s", "gossip_msgs_s_per_agent", "rss_mb_per_agent", "notes"],
         figure="F8"),
    dict(id="E9", part="B", section="8.5", title="Fault tolerance and coordinator election",
         rq="RQ3", contrib="C2",
         factors="failure scenario (4) × election policy (4) × agents 4/8/16/32; plus 20-min churn run (one leave + one join every 30 s)",
         reps=50, duration="per trial until recovery + 60 s",
         hypothesis="H9: fitness-proportionate voting over reputation elects coordinators with a mean quality ratio >= 0.95 at < 2× the election time of random selection; availability during coordinator failure stays >= 99%.",
         raw=["trial_id", "scenario", "agents", "policy", "detect_s", "elect_s", "recover_s", "availability_pct", "lost_ack_writes", "quality_ratio", "notes"],
         figure="F9"),
    dict(id="E10", part="B", section="8.5", title="Identity and access-control overhead",
         rq="RQ2", contrib="C4",
         factors="access control off/on × operation read/write × outcome (granted + five denial causes); plus revocation propagation for 4-32 agents",
         reps=10, duration="200 operations per cell",
         hypothesis="H10: verifying a Verifiable Presentation adds < 5 ms to a granted operation; every denial is returned before any data access; revocations reach all agents within the convergence time measured in E5.",
         raw=["run_id", "ac_mode", "operation", "outcome", "rep", "mean_ms", "p99_ms", "verify_us", "notes"],
         figure="F10"),
    dict(id="E11", part="B", section="8.5", title="AI-assisted metadata enrichment",
         rq="RQ1", contrib="C5",
         factors="field (5) on a held-out annotated corpus; TinyLlama 1.1B (4-bit GGUF) vs rule-based extractor; tier cloud/fog/edge; synchronous vs asynchronous enrichment",
         reps=3, duration="whole test split",
         hypothesis="H11: TinyLlama reaches F1 >= 0.80 on resource type and deployment tier and outperforms the rule-based extractor; asynchronous enrichment removes inference latency from the ingest path.",
         raw=["doc_id", "field", "extractor", "tp", "fp", "fn", "notes"],
         figure="F11"),
]

EXTRA_RAW = {
    "E9_churn": ["t_s", "rep", "throughput_ops_s", "event", "notes"],
    "E10_revocation": ["run_id", "agents", "rep", "propagation_s", "notes"],
    "E11_latency": ["run_id", "tier", "mode", "doc_id", "rep", "latency_ms", "tokens_out", "notes"],
    "E11_agreement": ["field", "both_yes", "a_yes_b_no", "a_no_b_yes", "both_no"],
}

METRICS = [
    ("Latency", "ms", "Time from the operation's scheduled start (open loop, avoids coordinated omission) to the client receiving the full response."),
    ("Percentiles P50/P95/P99/P99.9", "ms", "Computed per run from all operations after warm-up (HDR histogram, 3 significant digits); reported as the mean over runs with a 95% CI."),
    ("Achieved throughput", "ops/s", "Successfully completed operations per second during the measured window."),
    ("Saturation throughput", "ops/s", "Highest offered load at which achieved ≥ 99% of offered and P99 ≤ 500 ms."),
    ("Completeness", "%", "|returned ∩ ground truth| / |ground truth|, where ground truth is the union of all replicas after quiescence."),
    ("Staleness", "s", "Age of the newest write missing from a result, measured against the writer's timestamp (NTP-synchronised clocks, offset logged)."),
    ("Convergence time", "s", "From partition heal (or last write) until all replicas report the same state hash."),
    ("Acknowledged-write loss", "count", "Writes acknowledged to a client that are absent from the converged state of every replica."),
    ("Detection / election / recovery time", "s", "Fault injection → first agent suspects failure → announcement of new coordinator → first successful distributed query."),
    ("Availability", "%", "Successful operations / attempted operations during the fault window."),
    ("Election quality ratio", "–", "R(elected) / max R over live candidates, using reputation snapshots taken at fault injection."),
    ("Verification cost", "µs", "Server-side time spent in the six credential checks, from agent instrumentation."),
    ("Precision / recall / F1", "–", "Per field against adjudicated gold annotations of the held-out split."),
    ("Resource usage", "% / MB", "CPU and RSS of the database process (cgroup accounting), sampled at 1 Hz."),
]

PRINCIPLES = [
    # Papadopoulos et al., IEEE TSE 2021
    ("P1 Repeated experiments", "Every cell repeated 5–50 times on fresh deployments; repetitions interleaved across systems to spread temporal cloud noise."),
    ("P2 Workload and configuration coverage", "YCSB-style mixes, four document sizes, four data volumes, agent counts 4–64, and fault scenarios."),
    ("P3 Experimental setup description", "Testbed, workloads, systems and experiment matrix in Tables 7-10 of the paper and in the artefact."),
    ("P4 Open access artefact", "Harness, configurations, raw results and this workbook archived with a DOI."),
    ("P5 Probabilistic result description", "Means with 95% CIs, P50–P99.9 percentiles and CDFs instead of single values."),
    ("P6 Statistical evaluation", "Welch t-test or Mann–Whitney U (normality via Shapiro–Wilk), Cliff's δ effect size, Holm–Bonferroni correction."),
    ("P7 Measurement units", "Units given for every metric (sheet Metrics)."),
    ("P8 Cost", "Instance hours and device counts reported per experiment."),
]
