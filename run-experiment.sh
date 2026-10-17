#!/usr/bin/env bash
# Bench host: run one common scenario. Usage: run-experiment.sh E1..E6 [--reps N] [--systems a b] [--follow] [--no-netem] [--pilot]
source "$(dirname "$0")/scripts/lib/common.sh"
EXP="${1:?usage: run-experiment.sh E1..E6 [--reps N] [--systems ...] [--follow] [--no-netem] [--pilot]}"; shift
case "$EXP" in E1|E2|E3|E4|E5|E6) ;; *) die "only the common scenarios E1-E6 are supported";; esac
REPS=""; SYS=(); FOLLOW=0; NETEM=1; PILOT=0
while [ $# -gt 0 ]; do case "$1" in
  --reps) REPS="$2"; shift 2;; --follow) FOLLOW=1; shift;; --no-netem) NETEM=0; shift;; --pilot) PILOT=1; shift;;
  --systems) shift; while [ $# -gt 0 ] && [[ "$1" != --* ]]; do SYS+=("$1"); shift; done;;
  *) die "unknown option $1";; esac; done
TAG=""; [ $PILOT = 1 ] && TAG="-pilot"
LOG="/results/logs/$EXP$TAG-$(date +%Y%m%d-%H%M%S).log"
if [ "$EXP" = E6 ]; then
  [ -f "$ROOT/trace/trace.jsonl" ] || die "E6 needs trace/trace.jsonl"
  CMD="python -m bench.trace --campaign --trace /trace/trace.jsonl --config /config/testbed.yaml"
else CMD="python -m bench.runner $EXP --config /config/testbed.yaml"; [ $PILOT = 1 ] && CMD="$CMD --pilot"; fi
[ -n "$REPS" ] && CMD="$CMD --reps $REPS"
[ ${#SYS[@]} -gt 0 ] && CMD="$CMD --systems ${SYS[*]}"
[ $NETEM = 1 ] && { step "Applying the Table 7 link profiles"; bench python -m bench.cluster netem --config /config/testbed.yaml; }
step "Running $EXP (log: results/logs/$(basename "$LOG"))"
docker exec -d odb-bench sh -c "$CMD > $LOG 2>&1"
if [ $FOLLOW = 1 ]; then sleep 1; docker exec odb-bench tail -n +1 -f "$LOG"; else echo "Follow with: docker exec odb-bench tail -f $LOG"; fi
