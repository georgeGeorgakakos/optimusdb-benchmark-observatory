#!/usr/bin/env bash
# Stops the running experiment or campaign chain (finished runs are kept; re-run the same command to resume).
source "$(dirname "$0")/scripts/lib/common.sh"
assert_docker
docker exec odb-bench pkill -f 'logs/campaign' >/dev/null 2>&1 || true
docker exec odb-bench pkill -f '^python -m bench' >/dev/null 2>&1 || true
sleep 2; docker exec odb-bench python -m bench.cluster stop-all --config /config/testbed.yaml >/dev/null 2>&1 || true
ok "Experiment stopped and all data stores stopped. Finished runs are kept in results/."
