#!/usr/bin/env bash
# Baseline calibration (see calibrate-baselines.ps1). SYSTEMS=gun,autobase,opendht RATES=5,10,25,50 RECORDS=10000
set -euo pipefail
cd "$(dirname "$0")"
docker exec -i -e "SYSTEMS=${SYSTEMS:-gun,autobase,opendht}" -e "WORKLOADS=${WORKLOADS:-WA,WO}" -e "RATES=${RATES:-5,10,25,50}" \
  -e "RECORDS=${RECORDS:-10000}" -e "CLUSTER_NETEM=${CLUSTER_NETEM:-1}" -e "AUTOBASE_INDEXERS=${AUTOBASE_INDEXERS:-}" \
  odb-bench python - < tools/calibrate_baselines.py
ls -t results/logs/calibration-*.txt | head -1
