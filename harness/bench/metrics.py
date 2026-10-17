"""Per-run summaries and between-system statistics.

Follows Papadopoulos et al. (IEEE TSE 2021) and Hoefler & Belli (SC'15):
repetitions are the unit of analysis; percentiles are computed within a run and
compared across runs; tests are non-parametric unless normality holds; effect
sizes are reported next to p-values; multiple comparisons are Holm-corrected.
"""
import math
import numpy as np
from scipy import stats


def run_summary(records, measured_s):
    # Operations the system's interface cannot express (NotImplementedError, e.g. predicate queries on a DHT)
    # are counted separately: they are neither errors nor latency samples.
    unsupported = sum(1 for r in records if not r.ok and r.err.startswith("NotImplementedError"))
    records = [r for r in records if r.ok or not r.err.startswith("NotImplementedError")]
    # share of the offered operations the interface supports: throughput is compared with offered x share
    share = round(len(records) / (len(records) + unsupported), 4) if (records or unsupported) else 1.0
    ok = [r.latency_ms for r in records if r.ok]
    n_err = sum(1 for r in records if not r.ok)
    if not ok:
        return dict(ops=len(records), errors=n_err, mean_ms=None, p50_ms=None, p95_ms=None,
                    p99_ms=None, p999_ms=None, achieved_ops_s=0.0, unsupported=unsupported, supported_share=share)
    a = np.asarray(ok)
    return dict(ops=len(records), errors=n_err, unsupported=unsupported, supported_share=share,
                mean_ms=round(float(a.mean()), 3),
                p50_ms=round(float(np.percentile(a, 50)), 3),
                p95_ms=round(float(np.percentile(a, 95)), 3),
                p99_ms=round(float(np.percentile(a, 99)), 3),
                p999_ms=round(float(np.percentile(a, 99.9)), 3),
                achieved_ops_s=round(len(ok) / measured_s, 3))


def ci95(values):
    v = np.asarray([x for x in values if x is not None], float)
    if len(v) < 2:
        return (float(v.mean()) if len(v) else math.nan, math.nan)
    h = stats.t.ppf(0.975, len(v) - 1) * v.std(ddof=1) / math.sqrt(len(v))
    return float(v.mean()), float(h)


def bootstrap_ci(values, stat=np.median, n=10000, seed=1):
    v = np.asarray(values, float)
    rng = np.random.default_rng(seed)
    bs = stat(rng.choice(v, (n, len(v)), replace=True), axis=1)
    return float(stat(v)), float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))


def cliffs_delta(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    gt = sum((x > b).sum() for x in a)
    lt = sum((x < b).sum() for x in a)
    d = (gt - lt) / (len(a) * len(b))
    ad = abs(d)
    mag = "negligible" if ad < 0.147 else "small" if ad < 0.33 else "medium" if ad < 0.474 else "large"
    return float(d), mag   # thresholds: Romano et al. (2006)


def compare(a, b, alpha=0.05):
    """Two independent samples of run-level values."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    normal = (len(a) >= 3 and len(b) >= 3 and stats.shapiro(a).pvalue > alpha and stats.shapiro(b).pvalue > alpha)
    if normal:
        test, p = "welch_t", float(stats.ttest_ind(a, b, equal_var=False).pvalue)
    else:
        test, p = "mann_whitney_u", float(stats.mannwhitneyu(a, b, alternative="two-sided").pvalue)
    d, mag = cliffs_delta(a, b)
    return dict(test=test, p_raw=p, cliffs_delta=d, magnitude=mag,
                mean_a=float(a.mean()), mean_b=float(b.mean()),
                diff_pct=float((a.mean() - b.mean()) / b.mean() * 100) if b.mean() else math.nan)


def holm(pvals, alpha=0.05):
    order = np.argsort(pvals)
    m = len(pvals); adj = [0.0] * m; running = 0.0
    for rank, idx in enumerate(order):
        running = max(running, min(1.0, (m - rank) * pvals[idx]))
        adj[idx] = running
    return adj, [p <= alpha for p in adj]
