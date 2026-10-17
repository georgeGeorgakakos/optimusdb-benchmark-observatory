#!/usr/bin/env bash
# Stops and removes this host's testbed containers. Usage: stop-host.sh <host-name> [--purge]
source "$(dirname "$0")/scripts/lib/common.sh"
NAME="${1:?usage: stop-host.sh <host-name> [--purge]}"; HD="$(host_dir "$NAME")"; export HOST_DIR="$HD"
F=host.compose.yml; if [ "$(env_get "$HD/.env" ROLE)" = bench ]; then F=bench.compose.yml; export RESULTS_DIR="$ROOT/results" TRACE_DIR="$ROOT/trace"; fi
if [ "${2:-}" = --purge ]; then compose $F "$HD/.env" down -v; else compose $F "$HD/.env" down; fi
ok "Stopped $NAME"
