#!/usr/bin/env bash
# Bench host: apply (default) or clear (--clear) the Table 7 link profiles.
source "$(dirname "$0")/scripts/lib/common.sh"
if [ "${1:-}" = --clear ]; then bench python -m bench.cluster clear-netem --config /config/testbed.yaml
else bench python -m bench.cluster netem --config /config/testbed.yaml; fi
