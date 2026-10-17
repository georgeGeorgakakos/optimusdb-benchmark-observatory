#!/usr/bin/env bash
# Keeps a copy of results/ in results-archive/<date-time>[-<name>]/ (viewable in the dashboard's Run history).
#   ./save-results.sh [--name LABEL] [--move]      --move empties results/ so the next run starts from zero
set -u
. "$(dirname "$0")/scripts/lib/common.sh"
NAME=""; MOVE=0
while [ $# -gt 0 ]; do case "$1" in --name) NAME="$2"; shift 2;; --move) MOVE=1; shift;; *) shift;; esac; done
[ -n "$NAME" ] && ! [[ "$NAME" =~ ^[A-Za-z0-9_-]+$ ]] && die "name: use letters, digits, - and _ only"
[ -d "$ROOT/results" ] || die "There is no results/ folder yet."
docker exec odb-bench sh -c "pgrep -f '^python -m bench' >/dev/null" 2>/dev/null && die "An experiment is running: wait until it finishes, then save."
DST="$ROOT/results-archive/$(date +%Y%m%d-%H%M%S)${NAME:+-$NAME}"; mkdir -p "$ROOT/results-archive"
if [ $MOVE = 1 ]; then mv "$ROOT/results" "$DST"; mkdir -p "$ROOT/results/logs"; ok "Results moved to $DST; results/ is empty"
else cp -a "$ROOT/results" "$DST"; ok "Results copied to $DST"; fi
