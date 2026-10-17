#!/usr/bin/env bash
# Single-machine mode: one command from any state to a clean, verified testbed (see fresh-start.ps1).
# Usage: fresh-start.sh [--rebuild] [--delete-results] [--skip-smoke]
#                       [--cpus-cloud 1.5 --mem-cloud 3g --cpus-fog 1.5 --mem-fog 3g --cpus-edge 1 --mem-edge 2g]
# Limits default to the previous deployment, else cloud/fog 1.5 CPU 3g, edge 1 CPU 2g.
source "$(dirname "$0")/scripts/lib/common.sh"
cd "$ROOT"
REBUILD=0; DELRES=0; SMOKE=1; declare -A L=()
while [ $# -gt 0 ]; do case "$1" in
  --rebuild) REBUILD=1; shift;; --delete-results) DELRES=1; shift;; --skip-smoke) SMOKE=0; shift;;
  --cpus-*|--mem-*) L["${1#--}"]="$2"; shift 2;; *) die "unknown option $1";; esac; done
STAMP=$(date +%Y%m%d-%H%M%S); TMPLOG=$(mktemp /tmp/odb-fresh-start-XXXX.log)
exec > >(tee -a "$TMPLOG") 2>&1

step "Checking Docker"; assert_docker; ok "Docker is running"

C="$ROOT/compose/local.compose.yml"
prev() {  # prev <tier> <cpus|mem_limit>
  [ -f "$C" ] && tail -n +2 "$C" | python3 -c "import json,sys; s=json.load(sys.stdin)['services']; \
print(next((str(v['$2']) for k,v in s.items() if k.startswith('optimusdb-$1-')),''))" 2>/dev/null || true
}
GEN=()
for t in cloud fog edge; do
  dc=1.5; dm=3g; [ $t = edge ] && { dc=1; dm=2g; }
  c=${L[cpus-$t]:-$(prev $t cpus)}; m=${L[mem-$t]:-$(prev $t mem_limit)}
  GEN+=(--cpus-$t "${c:-$dc}" --mem-$t "${m:-$dm}")
done
ok "Limits per data store: ${GEN[*]}"

step "Removing the old testbed"
if [ "$(docker inspect --type container -f '{{.State.Running}}' odb-bench 2>/dev/null)" = true ]; then
  docker exec odb-bench pkill -f 'logs/campaign' >/dev/null 2>&1 || true
  docker exec odb-bench pkill -f '^python -m bench' >/dev/null 2>&1 || true; ok "Stopped any running experiment"
fi
[ -f "$C" ] && docker compose -f "$C" down -v --remove-orphans
LEFT=$(docker ps -aq --filter 'name=^odb-'); [ -n "$LEFT" ] && docker rm -f $LEFT >/dev/null
VOLS=$(docker volume ls -q --filter label=com.docker.compose.project=odb-local); [ -n "$VOLS" ] && docker volume rm -f $VOLS >/dev/null
docker network rm odbnet >/dev/null 2>&1 || true
ok "Containers, data volumes and network removed"

if [ -d results ] && [ -n "$(find results -type f ! -name 'fresh-start-*' 2>/dev/null)" ]; then
  if [ $DELRES = 1 ]; then rm -rf results; ok "Old results deleted"
  else mkdir -p results-archive; mv results "results-archive/$STAMP"; ok "Old results moved to results-archive/$STAMP"; fi
fi
mkdir -p results/logs

DL=()
if [ $REBUILD = 1 ]; then
  step "Full rebuild: removing the OptimusDB clone and the testbed images"
  rm -rf .src
  IMGS=$(docker images -q --filter 'reference=odb-*' | sort -u); [ -n "$IMGS" ] && docker rmi -f $IMGS >/dev/null
  DL+=(--no-cache)
fi
ODB_FRESH_START=1 "$ROOT/deploy-local.sh" "${DL[@]}" "${GEN[@]}" || die "deploy-local failed (see above)"

FAILED=()
if [ $SMOKE = 1 ]; then
  declare -A RES=() SEC=()
  for s in "${SYSTEMS[@]}"; do
    step "Smoke test: $s"
    out=$(docker exec odb-bench python -m bench.cluster deploy "$s" --config /config/testbed.yaml 2>&1) && code=0 || code=$?
    echo "$out"
    if [ $code = 0 ]; then RES[$s]=PASS; else RES[$s]=FAIL; FAILED+=("$s"); fi
    SEC[$s]=$(echo "$out" | grep -o '"smoke_s": *[0-9.]*' | grep -o '[0-9.]*$' || true)
  done
  docker exec odb-bench python -m bench.cluster stop-all --config /config/testbed.yaml >/dev/null 2>&1
  step "Smoke test summary"
  printf '  %-10s %-6s %s\n' System Result "Visible on last host (s)"
  for s in "${SYSTEMS[@]}"; do printf '  %-10s %-6s %s\n' "$s" "${RES[$s]}" "${SEC[$s]}"; done
  if [ ${#FAILED[@]} -gt 0 ]; then fail "Failed: ${FAILED[*]}. Logs: docker logs --tail 50 odb-cloud-a-<system>"
  else ok "All six data stores form a cluster and replicate"; fi
fi
echo
if [ ${#FAILED[@]} -gt 0 ]; then echo "Testbed is up, but fix the failed systems before the campaign (send the logs above)."
else echo "Fresh testbed ready. Next: ./run-all.sh --pilot   then   ./progress.sh --watch"; fi
cp "$TMPLOG" "results/logs/fresh-start-$STAMP.log" && echo "Log: results/logs/fresh-start-$STAMP.log"
