#!/usr/bin/env bash
# Progress of the running (or last) experiment. Usage: progress.sh [E1..E6] [--watch]
cd "$(dirname "$0")"
EXP=""; WATCH=0
for a in "$@"; do case "$a" in --watch) WATCH=1;; E[1-6]) EXP=$a;; *) echo "usage: progress.sh [E1..E6] [--watch]"; exit 1;; esac; done
show() {
  log=$(ls -t results/logs/${EXP:-E}*-*.log 2>/dev/null | grep -v fresh-start | head -1)
  [ -z "$log" ] && { echo "No experiment log yet. Start with ./run-all.sh --pilot"; return; }
  e=$(basename "$log" | cut -d- -f1); RD=results; case "$log" in *-pilot-*) RD=results/pilot;; *-quick-*) RD=results/quick;; esac
  camp=$(ls -t results/logs/campaign*.log 2>/dev/null | head -1)
  [ -n "$camp" ] && { echo; echo "Chain ($camp):"; sed 's/^/  /' "$camp"; }
  if docker exec odb-bench sh -c "pgrep -f '^python -m bench' >/dev/null" 2>/dev/null; then st=RUNNING; else st="NOT RUNNING"; fi
  echo; echo "$e  $st   log: $log"
  pos=$(grep -E '\[[0-9]+/[0-9]+\]' "$log" | tail -1); [ -n "$pos" ] && echo "  at: $pos"
  last=$(tail -1 "$log"); [ -n "$last" ] && [ "$last" != "$pos" ] && echo "  now: $last"
  if [ -f "$RD/${e}_raw.csv" ]; then
    echo "  finished runs: $(( $(wc -l < "$RD/${e}_raw.csv") - 1 ))"
    python3 - "$RD/${e}_raw.csv" <<'PY' 2>/dev/null || true
import csv, sys, collections
c = collections.Counter(r["system"] for r in csv.DictReader(open(sys.argv[1])))
for k in sorted(c): print(f"    {k:10} {c[k]}")
PY
  fi
  nf=$(grep -c " $e-" $RD/failures.log 2>/dev/null || true); echo "  failed runs ($e): ${nf:-0}"
}
if [ $WATCH = 1 ]; then while true; do clear; show; echo; echo "(refreshes every 30 s; Ctrl+C stops watching only)"; sleep 30; done; else show; fi
