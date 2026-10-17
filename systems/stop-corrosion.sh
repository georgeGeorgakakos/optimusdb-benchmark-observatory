#!/usr/bin/env bash
# Bench host: Stops corrosion on every agent host (data is kept).  Usage: stop-corrosion.sh [--tier cloud|fog|edge]
source "$(dirname "$0")/../scripts/lib/common.sh"
bench python -m bench.cluster stop corrosion --config /config/testbed.yaml "$@"
