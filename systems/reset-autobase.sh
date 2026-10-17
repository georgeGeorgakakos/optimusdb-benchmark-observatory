#!/usr/bin/env bash
# Bench host: Stops everything, wipes the autobase data on every host, then starts, joins and smoke-tests autobase (what the harness does before each run).  Usage: reset-autobase.sh [--tier cloud|fog|edge]
source "$(dirname "$0")/../scripts/lib/common.sh"
bench python -m bench.cluster reset autobase --config /config/testbed.yaml "$@"
