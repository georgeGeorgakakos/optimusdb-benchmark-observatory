#!/usr/bin/env bash
# Bench host: Stops autobase on every agent host (data is kept).  Usage: stop-autobase.sh [--tier cloud|fog|edge]
source "$(dirname "$0")/../scripts/lib/common.sh"
bench python -m bench.cluster stop autobase --config /config/testbed.yaml "$@"
