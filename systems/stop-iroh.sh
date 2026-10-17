#!/usr/bin/env bash
# Bench host: Stops iroh on every agent host (data is kept).  Usage: stop-iroh.sh [--tier cloud|fog|edge]
source "$(dirname "$0")/../scripts/lib/common.sh"
bench python -m bench.cluster stop iroh --config /config/testbed.yaml "$@"
