#!/usr/bin/env bash
# Bench host: Stops everything, wipes the opendht data on every host, then starts, joins and smoke-tests opendht (what the harness does before each run).  Usage: reset-opendht.sh [--tier cloud|fog|edge]
source "$(dirname "$0")/../scripts/lib/common.sh"
bench python -m bench.cluster reset opendht --config /config/testbed.yaml "$@"
