#!/usr/bin/env bash
# Bench host: Stops optimusdb on every agent host (data is kept).  Usage: stop-optimusdb.sh [--tier cloud|fog|edge]
source "$(dirname "$0")/../scripts/lib/common.sh"
bench python -m bench.cluster stop optimusdb --config /config/testbed.yaml "$@"
