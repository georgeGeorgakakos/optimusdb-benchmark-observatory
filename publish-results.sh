#!/usr/bin/env bash
# Builds the dashboard snapshot (site/), commits results + snapshot and pushes (see publish-results.ps1).
# Usage: ./publish-results.sh [-m "message"] [--no-push] [--build-only] [--no-ops]
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"; MSG=""; PUSH=1; BUILD_ONLY=0; EXTRA=()
while [ $# -gt 0 ]; do case "$1" in
  -m) MSG="$2"; shift 2;; --no-push) PUSH=0; shift;; --build-only) BUILD_ONLY=1; shift;; --no-ops) EXTRA+=(--no-ops); shift;;
  *) echo "unknown option $1"; exit 1;; esac; done
if docker image inspect odb-bench:latest >/dev/null 2>&1; then
  docker run --rm -v "$ROOT:/work" -w /work --entrypoint python odb-bench:latest tools/build_site.py --results results --archive results-archive --out site "${EXTRA[@]}"
else
  python3 "$ROOT/tools/build_site.py" "${EXTRA[@]}"
fi
[ $BUILD_ONLY = 1 ] && exit 0
cd "$ROOT"; [ -d .git ] || { echo "not a Git repository yet (README-GITHUB.md, step 2)"; exit 1; }
git add -A results results-archive site
git diff --cached --quiet || git commit -m "${MSG:-Results $(date '+%Y-%m-%d %H:%M')}"
[ $PUSH = 1 ] && git push
