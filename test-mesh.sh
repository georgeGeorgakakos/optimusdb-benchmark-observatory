#!/usr/bin/env bash
# Bench host: agent reachability, clock offsets and overlay ping matrix.
source "$(dirname "$0")/scripts/lib/common.sh"
bench python -m bench.cluster mesh --config /config/testbed.yaml
