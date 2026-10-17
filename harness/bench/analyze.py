"""Statistics over results/*.csv -> results/stats_<E>.csv (paste into the Stats sheet) and CDF data.

python -m bench.analyze E1 --metric p99_ms --group workload doc_size --baseline optimusdb
"""
import argparse, glob, os
import numpy as np, pandas as pd
from .metrics import compare, holm, ci95

RES = os.environ.get("BENCH_RESULTS", "results")


def pairwise(df, exp, metric, group, key="system", ref="optimusdb"):
    rows = []
    for g, sub in df.groupby(list(group)):
        a = sub[sub[key] == ref][metric].dropna().astype(float).values
        for other, s2 in sub[sub[key] != ref].groupby(key):
            b = s2[metric].dropna().astype(float).values
            if len(a) < 2 or len(b) < 2: continue
            r = compare(a, b); rows.append(dict(experiment=exp, metric=metric, condition=", ".join(f"{c}={v}" for c, v in zip(group, g if isinstance(g, tuple) else (g,))), system_a=ref, system_b=other,
                                                n_a=len(a), n_b=len(b), **r))
    if rows:
        adj, sig = holm([r["p_raw"] for r in rows])
        for r, p, s in zip(rows, adj, sig): r["p_holm"], r["significant"] = p, s
    return pd.DataFrame(rows)


def cdf(exp, tag_glob, out):
    """Pool per-op latencies of matching runs into a CDF table (percentile grid)."""
    grid = [1, 5, 10, 25, 50, 75, 90, 95, 99, 99.9]
    rows = []
    for f in sorted(glob.glob(f"{RES}/ops/{tag_glob}.csv")):
        lat = pd.read_csv(f).query("ok == 1")["latency_ms"].values
        rows.append(dict(run=os.path.basename(f)[:-4], **{f"p{q}": float(np.percentile(lat, q)) for q in grid}))
    pd.DataFrame(rows).to_csv(out, index=False)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("exp"); ap.add_argument("--metric", default="p99_ms")
    ap.add_argument("--group", nargs="+", default=["workload"]); ap.add_argument("--key", default="system"); ap.add_argument("--baseline", default="optimusdb")
    a = ap.parse_args()
    df = pd.read_csv(f"{RES}/{a.exp}_raw.csv")
    st = pairwise(df, a.exp, a.metric, a.group, a.key, a.baseline)
    cols = ["experiment", "metric", "condition", "system_a", "system_b", "n_a", "n_b", "mean_a", "mean_b", "diff_pct", "test", "p_raw", "p_holm", "cliffs_delta", "magnitude", "significant"]
    out = f"{RES}/stats_{a.exp}_{a.metric}.csv"; st.reindex(columns=cols).to_csv(out, index=False); print(out, len(st), "comparisons")
    cdf(a.exp, f"{a.exp}-*", f"{RES}/cdf_{a.exp}.csv")


if __name__ == "__main__":
    main()
