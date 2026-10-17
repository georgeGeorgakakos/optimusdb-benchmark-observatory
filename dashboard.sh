#!/usr/bin/env bash
# Starts the OptimusDB benchmark dashboard (ICCS) on http://localhost:8501.   ./dashboard.sh [--port N] [--stop]
set -u
. "$(dirname "$0")/scripts/lib/common.sh"
PORT=8501; STOP=0
while [ $# -gt 0 ]; do case "$1" in --port) PORT="$2"; shift 2;; --stop) STOP=1; shift;; *) shift;; esac; done
assert_docker
docker rm -f odb-dashboard >/dev/null 2>&1
[ $STOP = 1 ] && { ok "Dashboard stopped"; exit 0; }
docker image inspect odb-bench:latest >/dev/null 2>&1 || die "Image odb-bench:latest not found. Run ./fresh-start.sh first."
mkdir -p "$ROOT/results/logs" "$ROOT/results-archive"
PID=(); [ "$(docker inspect --type container -f '{{.State.Status}}' odb-bench 2>/dev/null)" = running ] && PID=(--pid container:odb-bench)
docker run -d --name odb-dashboard -p 127.0.0.1:$PORT:8501 -v "$ROOT/results:/results:ro" -v "$ROOT/results-archive:/archive:ro" -v "$ROOT/dashboard:/app:ro" \
  "${PID[@]}" --entrypoint python odb-bench:latest /app/server.py --results /results --archive /archive >/dev/null || die "Could not start the dashboard"
ok "Dashboard: http://localhost:$PORT   (stop: ./dashboard.sh --stop)"
