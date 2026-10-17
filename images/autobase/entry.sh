#!/bin/bash
# Direct TCP replication between the overlay addresses in PEERS (no Hyperswarm DHT needed on the testbed).
set -a; [ -f /runtime/autobase.env ] && . /runtime/autobase.env; set +a
export PORT=7005 REPL_PORT=7305 DATA_DIR=/data/store PEERS="${PEERS:-}"
# Node.js heap = 85 % of the container's memory limit. Node's default heap (~1.5-2 GB) is independent of the
# limit, so without this a Node store could die of "heap out of memory" while its container still had memory.
lim=$(cat /sys/fs/cgroup/memory.max 2>/dev/null || cat /sys/fs/cgroup/memory/memory.limit_in_bytes 2>/dev/null || echo max)
if [ "$lim" != "max" ] && [ "$lim" -lt 1000000000000 ] 2>/dev/null; then
  export NODE_OPTIONS="--max-old-space-size=$(( lim / 1048576 * 85 / 100 )) ${NODE_OPTIONS:-}"
fi
exec node /app/autobase_http.mjs
