#!/usr/bin/env bash
# Profiles OptimusDB under WA (or WORKLOAD=..., RATE=...); result: results/logs/profile-<time>.zip
set -euo pipefail
cd "$(dirname "$0")"
args=(-e "WORKLOAD=${WORKLOAD:-WA}"); [ -n "${RATE:-}" ] && args+=(-e "RATE=$RATE")
out=$(docker exec -i "${args[@]}" odb-bench python - < tools/profile_optimusdb.py 2>&1 | tee /dev/stderr)
name=$(printf '%s\n' "$out" | sed -n 's/^PROFILE_DIR //p' | tail -1)
[ -n "$name" ] || { echo "No profile was collected." >&2; exit 1; }
docker logs --tail 60 odb-cloud-a-optimusdb > "results/logs/$name/cloud-a-container.log" 2>&1 || true
(cd results/logs && zip -qr "$name.zip" "$name")
echo "Profile: results/logs/$name.zip"
