#!/usr/bin/env bash
# Bench host: Stops everything, wipes the corrosion data on every host, then starts, joins and smoke-tests corrosion (what the harness does before each run).  Usage: reset-corrosion.sh [--tier cloud|fog|edge]
source "$(dirname "$0")/../scripts/lib/common.sh"
bench python -m bench.cluster reset corrosion --config /config/testbed.yaml "$@"
