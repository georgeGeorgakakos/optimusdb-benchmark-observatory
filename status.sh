#!/usr/bin/env bash
source "$(dirname "$0")/scripts/lib/common.sh"
bench python -m bench.cluster status --config /config/testbed.yaml
