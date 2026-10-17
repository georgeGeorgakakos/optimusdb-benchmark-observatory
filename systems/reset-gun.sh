#!/usr/bin/env bash
# Bench host: Stops everything, wipes the gun data on every host, then starts, joins and smoke-tests gun (what the harness does before each run).  Usage: reset-gun.sh [--tier cloud|fog|edge]
source "$(dirname "$0")/../scripts/lib/common.sh"
bench python -m bench.cluster reset gun --config /config/testbed.yaml "$@"
