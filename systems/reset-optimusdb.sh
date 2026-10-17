#!/usr/bin/env bash
# Bench host: Stops everything, wipes the optimusdb data on every host, then starts, joins and smoke-tests optimusdb (what the harness does before each run).  Usage: reset-optimusdb.sh [--tier cloud|fog|edge]
source "$(dirname "$0")/../scripts/lib/common.sh"
bench python -m bench.cluster reset optimusdb --config /config/testbed.yaml "$@"
