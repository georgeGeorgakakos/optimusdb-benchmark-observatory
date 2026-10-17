"""YCSB-style workload generation for orchestration metadata.

Key choice follows YCSB's scrambled Zipfian generator (Cooper et al., SoCC 2010),
so hot keys are spread over the key space instead of clustering at low ids.
"""
import json, math, random, string, hashlib

SIZE_BYTES = {"256B": 256, "2KB": 2048, "8KB": 8192, "64KB": 65536}

# (read, update, insert, query) shares
MIXES = {
    "WA": (0.50, 0.50, 0.00, 0.00),
    "WB": (0.95, 0.05, 0.00, 0.00),
    "WC": (1.00, 0.00, 0.00, 0.00),
    "WO": (0.60, 0.20, 0.10, 0.10),
}

REGIONS = ["eu-west", "eu-central", "eu-south", "eu-north"]
PROVIDERS = ["AWS", "Azure", "GCP", "OnPrem"]
STATUSES = ["Running", "Stopped", "Pending", "Degraded"]


class Zipfian:
    """Gray et al. 'Quickly generating billion-record synthetic databases' (as used by YCSB)."""

    def __init__(self, n, theta=0.99, rng=None):
        self.n, self.theta = n, theta
        self.rng = rng or random.Random()
        self.zetan = sum(1.0 / (i ** theta) for i in range(1, min(n, 100000) + 1))
        if n > 100000:  # integral approximation for the tail
            self.zetan += ((n ** (1 - theta)) - (100000 ** (1 - theta))) / (1 - theta)
        self.zeta2 = 1 + 0.5 ** theta
        self.alpha = 1.0 / (1.0 - theta)
        self.eta = (1 - (2.0 / n) ** (1 - theta)) / (1 - self.zeta2 / self.zetan)

    def next(self):
        u = self.rng.random()
        uz = u * self.zetan
        if uz < 1.0:
            return 0
        if uz < self.zeta2:
            return 1
        return int(self.n * ((self.eta * u - self.eta + 1) ** self.alpha)) % self.n


def scramble(i, n):
    h = int(hashlib.blake2b(str(i).encode(), digest_size=8).hexdigest(), 16)
    return h % n


def key_of(i):
    return f"res-{i:09d}"


def make_doc(i, size="2KB", rng=None, version=0):
    """A resource descriptor padded to the target size (JSON bytes)."""
    rng = rng or random.Random(i)
    doc = {
        "_id": key_of(i),
        # Attributes use independent digits of i (base 4), so predicates are uncorrelated: region, status, CPU and
        # memory each split the data in quarters, and Q2/Q3/Q5 have exact, non-trivial expected counts (see
        # expected_rows). With i % 4 for several fields, every eu-west resource had 2 CPUs and status Running.
        "resource_provider": PROVIDERS[(i // 256) % len(PROVIDERS)],
        "resource_type": ["Cloud", "Fog", "Edge"][i % 3],
        "status": STATUSES[((i // 64) + version) % len(STATUSES)],
        "region": REGIONS[i % len(REGIONS)],
        "cpu_capacity": [2, 4, 8, 16][(i // 4) % 4],
        "memory_capacity": [2048, 4096, 8192, 16384][(i // 16) % 4],
        "storage": 100 * (1 + i % 10),
        "version": version,
        "writer_ts": 0.0,
    }
    target = SIZE_BYTES[size]
    base = len(json.dumps(doc))
    if target > base + 12:
        doc["payload"] = "".join(rng.choices(string.ascii_letters, k=target - base - 12))
    return doc


def expected_rows(qid, records, allocations=10_000):
    """Exact row counts of Q1-Q5 (spec.QUERIES) over a fresh preload of `records` documents (version 0) plus the
    E3 allocation table, derived from make_doc. Used to mark E3 results correct or not."""
    if qid == "Q1":
        return 1
    if qid == "Q2":   # status = 'Running'
        return sum(1 for i in range(records) if (i // 64) % 4 == 0)
    if qid == "Q3":   # region = 'eu-west' AND cpu_capacity >= 4 AND memory_capacity >= 8192
        return sum(1 for i in range(records) if i % 4 == 0 and (i // 4) % 4 >= 1 and (i // 16) % 4 >= 2)
    if qid == "Q4":   # GROUP BY region
        return min(records, len(REGIONS))
    if qid == "Q5":   # allocations whose resource is in eu-west
        return sum(1 for i in range(allocations) if (i % records) % 4 == 0)
    raise ValueError(qid)


class Workload:
    def __init__(self, mix="WO", records=100_000, size="2KB", theta=0.99, seed=1,
                 hot_keys=None, contention=0.0):
        # constructor arguments, so a load-generator worker process can rebuild the same sequence
        self.args = ((mix, records, size, theta, seed), {"hot_keys": hot_keys, "contention": contention})
        self.mix = MIXES[mix]
        self.records, self.size = records, size
        self.rng = random.Random(seed)
        self.zipf = Zipfian(records, theta, self.rng)
        self.next_insert = records
        self.hot_keys = hot_keys          # E5: list of key indices shared by all writers
        self.contention = contention      # E5: share of writes that hit hot_keys
        self.version = 0

    def _key(self):
        return scramble(self.zipf.next(), self.records)

    def next_op(self):
        r = self.rng.random()
        rd, up, ins, q = self.mix
        if r < rd:
            return ("read", key_of(self._key()), None)
        if r < rd + up:
            if self.hot_keys and self.rng.random() < self.contention:
                i = self.rng.choice(self.hot_keys)
            else:
                i = self._key()
            self.version += 1
            return ("update", key_of(i), make_doc(i, self.size, self.rng, self.version))
        if r < rd + up + ins:
            i = self.next_insert; self.next_insert += 1
            return ("insert", key_of(i), make_doc(i, self.size, self.rng))
        region = self.rng.choice(REGIONS)
        return ("query", None, {"region": region, "status": "Running"})
