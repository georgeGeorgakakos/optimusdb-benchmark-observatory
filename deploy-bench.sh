#!/usr/bin/env bash
# Deploys the bench host (see deploy-bench.ps1). Usage: deploy-bench.sh [bench-name] [--no-build]
source "$(dirname "$0")/scripts/lib/common.sh"
NAME="${1:-bench}"; assert_docker; HD="$(host_dir "$NAME")"; E="$HD/.env"
[ "$(env_get "$E" ROLE)" = bench ] || die "$NAME is not the bench host"
export HOST_DIR="$HD" RESULTS_DIR="$ROOT/results" TRACE_DIR="$ROOT/trace"
mkdir -p "$RESULTS_DIR/logs" "$TRACE_DIR"; cd "$ROOT"
[ "${2:-}" = --no-build ] || { step "Building bench images"; compose bench.compose.yml "$E" build; }
step "Starting overlay endpoint and bench container"; compose bench.compose.yml "$E" up -d
sleep 3; docker exec odb-bench python -m pytest -q tests && ok "Harness self-test passed"
echo "Next: ./test-mesh.sh"
