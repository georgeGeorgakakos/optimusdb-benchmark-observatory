#!/usr/bin/env bash
# Bench host: Stops opendht on every agent host (data is kept).  Usage: stop-opendht.sh [--tier cloud|fog|edge]
source "$(dirname "$0")/../scripts/lib/common.sh"
bench python -m bench.cluster stop opendht --config /config/testbed.yaml "$@"
