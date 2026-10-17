#!/usr/bin/env bash
# Bench host: Stops gun on every agent host (data is kept).  Usage: stop-gun.sh [--tier cloud|fog|edge]
source "$(dirname "$0")/../scripts/lib/common.sh"
bench python -m bench.cluster stop gun --config /config/testbed.yaml "$@"
