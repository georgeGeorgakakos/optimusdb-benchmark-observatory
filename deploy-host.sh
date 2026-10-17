#!/usr/bin/env bash
# Deploys one agent host (see deploy-host.ps1). Usage: deploy-host.sh <host-name> [--no-build]
source "$(dirname "$0")/scripts/lib/common.sh"
NAME="${1:?usage: deploy-host.sh <host-name> [--no-build]}"; NOBUILD="${2:-}"
assert_docker; HD="$(host_dir "$NAME")"; E="$HD/.env"
[ "$(env_get "$E" ROLE)" != bench ] || die "$NAME is the bench host: use deploy-bench.sh"
export HOST_DIR="$HD"; cd "$ROOT"
if [ "$NOBUILD" != --no-build ]; then
  step "Building the OptimusDB base image from $(env_get "$E" OPTIMUSDB_SRC)"
  docker build -t odb-optimusdb-base:latest "$(resolve_optimus_source "$(env_get "$E" OPTIMUSDB_SRC)")"
  step "Building the testbed images"
  compose host.compose.yml "$E" build
fi
step "Starting overlay network and control agent"; compose host.compose.yml "$E" up -d net agent
step "Creating the data-store containers (stopped)"; compose host.compose.yml "$E" create "${SYSTEMS[@]}"
sleep 3
docker exec odb-net wg show wg0 && ok "WireGuard overlay is up" || fail "WireGuard did not start (docker logs odb-net)"
docker exec odb-agent wget -qO- --header "x-token: $(env_get "$E" AGENT_TOKEN)" http://127.0.0.1:9100/health | grep -q true \
  && ok "Agent listening on $(env_get "$E" OVERLAY_IP):9100" || fail "Agent not answering (docker logs odb-agent)"
