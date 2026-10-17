#!/usr/bin/env bash
# Runs several scenarios one after the other, unattended, inside the bench container (see run-all.ps1).
# Usage: run-all.sh [--pilot | --quick] [--exps E1 E2 ...] [--systems a b ...] [--workloads WO ...] [--new | --resume]
# Earlier results are kept automatically: a FINISHED previous run of the same kind whose experiments are run again
# is moved to results-archive/<start>-<kind>/; an interrupted one is continued; new experiments are added.
source "$(dirname "$0")/scripts/lib/common.sh"
assert_docker
PILOT=0; QUICK=0; EXPS=(); SYS=(); WLS=(); GIVEN=0; NEW=0; RESUME=0
while [ $# -gt 0 ]; do case "$1" in
  --pilot) PILOT=1; shift;;
  --quick) QUICK=1; shift;;
  --new) NEW=1; shift;;
  --resume) RESUME=1; shift;;
  --exps) GIVEN=1; shift; while [ $# -gt 0 ] && [[ "$1" != --* ]]; do EXPS+=("$1"); shift; done;;
  --systems) shift; while [ $# -gt 0 ] && [[ "$1" != --* ]]; do SYS+=("$1"); shift; done;;
  --workloads) shift; while [ $# -gt 0 ] && [[ "$1" != --* ]]; do WLS+=("$1"); shift; done;;
  *) die "unknown option $1";; esac; done
[ ${#EXPS[@]} -eq 0 ] && { if [ $PILOT = 1 ]; then EXPS=(E1); elif [ $QUICK = 1 ]; then EXPS=(E1 E2 E3 E4 E5); else EXPS=(E1 E2 E3 E4 E5 E6); fi; }
if [[ " ${EXPS[*]} " == *" E6 "* ]] && [ ! -f "$ROOT/trace/trace.jsonl" ]; then
  [ $GIVEN = 1 ] && die "E6 needs trace/trace.jsonl"
  warn "trace/trace.jsonl not found: E6 is skipped"; EXPS=("${EXPS[@]/E6}")
fi
[ $((PILOT + QUICK)) -gt 0 ] && [[ " ${EXPS[*]} " == *" E6 "* ]] && die "E6 has no pilot or quick mode"
docker exec odb-bench sh -c "pgrep -f '^python -m bench' >/dev/null" 2>/dev/null && die "An experiment is already running (progress.sh / stop-experiment.sh)"
# ---- keep earlier results automatically
KIND=campaign; T=""; [ $PILOT = 1 ] && { KIND=pilot; T="-pilot"; }; [ $QUICK = 1 ] && { KIND=quick; T="-quick"; }
RR="$ROOT/results"; mkdir -p "$RR/logs"; KD="$RR"; [ $KIND != campaign ] && KD="$RR/$KIND"
iskind() { local n; n=$(basename "$1"); if [ $KIND = campaign ]; then [[ "$n" =~ ^(campaign|E[0-9])-[0-9]{8}-[0-9]{6}\.log$ ]]; else [[ "$n" == *"$T-"*.log && "$n" != fresh-start-* ]]; fi; }
PREV=""; for f in $(ls "$RR"/logs/campaign*.log 2>/dev/null | sort); do iskind "$f" && PREV="$f"; done
HAVE=(); for e in "${EXPS[@]}"; do [ -n "$e" ] && [ -f "$KD/${e}_raw.csv" ] && HAVE+=("$e"); done
FIN=0; [ -n "$PREV" ] && grep -qE ' finished\s*$' "$PREV" && FIN=1
ARCH=0; if [ $RESUME = 1 ]; then ARCH=0; elif [ $NEW = 1 ]; then [ ${#HAVE[@]} -gt 0 ] && ARCH=1; else [ $FIN = 1 ] && [ ${#HAVE[@]} -gt 0 ] && ARCH=1; fi
if [ $ARCH = 1 ]; then
  LBL=$(basename "${PREV:-x}" | grep -oE '[0-9]{8}-[0-9]{6}' || date +%Y%m%d-%H%M%S); DST="$ROOT/results-archive/$LBL-$KIND"; i=2
  while [ -e "$DST" ]; do DST="$ROOT/results-archive/$LBL-$KIND-$i"; i=$((i+1)); done
  mkdir -p "$DST/logs"
  if [ $KIND = campaign ]; then for x in "$RR"/* "$RR"/.[!.]*; do [ -e "$x" ] || continue; case "$(basename "$x")" in quick|pilot|logs) ;; *) mv "$x" "$DST/";; esac; done
  else mv "$KD" "$DST/$KIND"; fi
  for f in "$RR"/logs/*.log; do [ -f "$f" ] && iskind "$f" && mv "$f" "$DST/logs/"; done
  FS=$(ls "$RR"/logs/fresh-start-*.log 2>/dev/null | sort | tail -1); [ -n "$FS" ] && cp "$FS" "$DST/logs/"
  ok "Previous $KIND run kept in results-archive/$(basename "$DST") (dashboard: Run history). Starting a new $KIND run."
elif [ -n "$PREV" ] && [ $FIN = 0 ] && [ ${#HAVE[@]} -gt 0 ]; then ok "Continuing the interrupted $KIND run: finished runs are skipped (--new starts over)."
elif [ ${#HAVE[@]} -gt 0 ]; then ok "Adding to the current $KIND results (${HAVE[*]} already there)."; fi

step "Applying the Table 7 link profiles"; bench python -m bench.cluster netem --config /config/testbed.yaml
STAMP=$(date +%Y%m%d-%H%M%S); TAG=""; [ $PILOT = 1 ] && TAG="-pilot"; [ $QUICK = 1 ] && TAG="-quick"
CLOG="/results/logs/campaign$TAG-$STAMP.log"
CHAIN="echo \$(date +%F_%T) start ${EXPS[*]}$TAG >> $CLOG"
for e in ${EXPS[@]}; do
  if [ "$e" = E6 ]; then CMD="python -m bench.trace --campaign --trace /trace/trace.jsonl --config /config/testbed.yaml"
  else CMD="python -m bench.runner $e --config /config/testbed.yaml"; [ $PILOT = 1 ] && CMD="$CMD --pilot"; [ $QUICK = 1 ] && CMD="$CMD --quick"; fi
  [ ${#SYS[@]} -gt 0 ] && CMD="$CMD --systems ${SYS[*]}"
  [ ${#WLS[@]} -gt 0 ] && [ "$e" = E1 ] && CMD="$CMD --workloads ${WLS[*]}"
  CHAIN="$CHAIN; echo \$(date +%F_%T) begin $e >> $CLOG; $CMD > /results/logs/$e$TAG-$STAMP.log 2>&1; echo \$(date +%F_%T) end $e exit=\$? >> $CLOG"
done
CHAIN="$CHAIN; echo \$(date +%F_%T) finished >> $CLOG"
CHAIN="$CHAIN; python /dashboard/report_cli.py --results /results --mode $KIND --stamp $STAMP > /results/logs/report$TAG-$STAMP.log 2>&1 || true"
docker exec -d odb-bench sh -c "$CHAIN"
ok "Started: ${EXPS[*]}$TAG. Watch: ./progress.sh --watch   Stop: ./stop-experiment.sh"
[ "$(docker inspect --type container -f '{{.State.Status}}' odb-dashboard 2>/dev/null)" = running ] || "$(dirname "$0")/dashboard.sh" >/dev/null 2>&1
echo "Dashboard: http://localhost:8501"
