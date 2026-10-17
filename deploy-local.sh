#!/usr/bin/env bash
# Single-machine mode (see deploy-local.ps1).
# Usage: deploy-local.sh [--no-build] [--no-cache] [--cpus-cloud 2 --mem-cloud 3g --cpus-fog 2 --mem-fog 3g --cpus-edge 1 --mem-edge 2g --subnet 10.88.0]
source "$(dirname "$0")/scripts/lib/common.sh"
NOBUILD=0; NC=(); GEN=()
while [ $# -gt 0 ]; do case "$1" in --no-build) NOBUILD=1; shift;; --no-cache) NC=(--no-cache); shift;; --*) GEN+=("$1" "$2"); shift 2;; *) die "unknown option $1";; esac; done
assert_docker; cd "$ROOT"
OPT_SRC="$(env_get versions.env OPTIMUSDB_SRC)"; CREF="$(env_get versions.env CORROSION_REF)"; DREF="$(env_get versions.env OPENDHT_REF)"
step "Docker VM: $(docker info --format '{{.NCPU}}') CPUs, $(( $(docker info --format '{{.MemTotal}}') / 1024 / 1024 / 1024 )) GB RAM"
if [ $NOBUILD = 0 ]; then
  step "Building images"
  docker build "${NC[@]}" -t odb-net:latest -f images/net/Dockerfile .
  docker build "${NC[@]}" -t odb-agent:latest -f images/agent/Dockerfile .
  docker build "${NC[@]}" -t odb-bench:latest -f images/bench/Dockerfile .
  docker build "${NC[@]}" -t odb-optimusdb-base:latest "$(resolve_optimus_source "$OPT_SRC")"
  docker build "${NC[@]}" -t odb-optimusdb:latest -f images/optimusdb/Dockerfile .
  docker build "${NC[@]}" -t odb-corrosion:latest --build-arg CORROSION_REF="$CREF" -f images/corrosion/Dockerfile .
  docker build "${NC[@]}" -t odb-gun:latest -f images/gun/Dockerfile .
  docker build "${NC[@]}" -t odb-autobase:latest -f images/autobase/Dockerfile .
  docker build "${NC[@]}" -t odb-iroh:latest -f images/iroh/Dockerfile .
  docker build "${NC[@]}" -t odb-opendht:latest --build-arg OPENDHT_REF="$DREF" -f images/opendht/Dockerfile .
fi
step "Generating the single-machine layout"
docker run --rm -v "$ROOT:/work" -w /work odb-net:latest python3 tools/gen_local.py "${GEN[@]}"
mkdir -p results/logs trace
C="$ROOT/compose/local.compose.yml"
mapfile -t SVC < <(docker compose -f "$C" config --services)
ALWAYS=(); STORES=()
for s in "${SVC[@]}"; do case "$s" in bench|net-*|agent-*) ALWAYS+=("$s");; *) STORES+=("$s");; esac; done
step "Starting bench, emulated hosts and agents"; docker compose -f "$C" up -d "${ALWAYS[@]}"
step "Creating ${#STORES[@]} data-store containers (stopped)"; docker compose -f "$C" create "${STORES[@]}"
sleep 5; docker exec odb-bench python -m pytest -q tests && ok "Harness self-test passed"
bench python -m bench.cluster mesh --config /config/testbed.yaml
[ -n "${ODB_FRESH_START:-}" ] || echo "Next: ./systems/deploy-gun.sh, then ./run-all.sh --pilot"
