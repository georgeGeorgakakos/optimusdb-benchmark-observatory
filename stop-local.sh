#!/usr/bin/env bash
# Single-machine mode: stop and remove all containers (--purge also deletes volumes).
source "$(dirname "$0")/scripts/lib/common.sh"
if [ "${1:-}" = --purge ]; then docker compose -f "$ROOT/compose/local.compose.yml" down -v; else docker compose -f "$ROOT/compose/local.compose.yml" down; fi
ok "Testbed stopped"
