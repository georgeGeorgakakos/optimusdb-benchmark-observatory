#!/usr/bin/env bash
# Generates out/<host>/ bundles and the harness config from hosts.csv (see gen-config.ps1).
source "$(dirname "$0")/scripts/lib/common.sh"
HOSTS="${1:-hosts.csv}"
assert_docker; cd "$ROOT"
[ -f "$HOSTS" ] || die "$HOSTS not found. Copy hosts.example.csv to hosts.csv and fill it in."
step "Building the network/tools image (odb-net)"
docker build -q -t odb-net:latest -f images/net/Dockerfile .
step "Generating bundles from $HOSTS"
docker run --rm -v "$ROOT:/work" -w /work odb-net:latest python3 tools/gen_config.py "$HOSTS" out
echo; echo "Next: copy this folder (with out/) to every host; run check-host and deploy-host there (bench host: deploy-bench)."
