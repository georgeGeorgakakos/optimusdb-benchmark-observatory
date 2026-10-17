#!/usr/bin/env bash
# Bench host: Starts gun on every agent host (other systems are stopped first), joins the nodes into one cluster and checks that a write on the first host is readable on the last.  Usage: deploy-gun.sh [--tier cloud|fog|edge]
source "$(dirname "$0")/../scripts/lib/common.sh"
bench python -m bench.cluster deploy gun --config /config/testbed.yaml "$@"
