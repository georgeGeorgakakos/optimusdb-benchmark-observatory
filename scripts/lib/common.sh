# Shared helpers for the bash scripts (Linux hosts or WSL).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SYSTEMS=(optimusdb corrosion gun autobase iroh opendht)
step() { printf '\033[36m==> %s\033[0m\n' "$*"; }
ok()   { printf '  \033[32m[OK]\033[0m   %s\n' "$*"; }
warn() { printf '  \033[33m[WARN]\033[0m %s\n' "$*"; }
fail() { printf '  \033[31m[FAIL]\033[0m %s\n' "$*"; }
die()  { echo "ERROR: $*" >&2; exit 1; }

assert_docker() {
  docker version --format '{{.Server.Os}}' >/dev/null 2>&1 || die "Docker is not running (docker version failed)."
  [ "$(docker version --format '{{.Server.Os}}')" = linux ] || die "Docker must run Linux containers."
}
env_get() { grep -E "^$2=" "$1" | head -1 | cut -d= -f2-; }
host_dir() {
  local d="$ROOT/out/$1"
  [ -f "$d/.env" ] || die "No bundle for '$1' in $ROOT/out. Run gen-config.sh first and copy the out folder to this host."
  (cd "$d" && pwd)
}
compose() { local file="$1" envf="$2"; shift 2; docker compose -f "$ROOT/compose/$file" --env-file "$envf" "$@"; }
bench() {
  if [ "$(docker inspect --type container -f '{{.State.Running}}' odb-bench 2>/dev/null)" != true ]; then
    docker info >/dev/null 2>&1 || die "Docker is not running. Start Docker, then try again."
    st=$(docker inspect --type container -f '{{.State.Status}}' odb-bench 2>/dev/null) || die "The odb-bench container does not exist. Single machine: ./deploy-local.sh   Multi-host: deploy-bench.sh on the bench host."
    die "odb-bench is $st. Start it with: docker start odb-bench (why it stopped: docker logs --tail 50 odb-bench)"
  fi
  docker exec odb-bench "$@"
}

resolve_optimus_source() {
  # git URL#ref -> clone into .src/optimusdb (git in a container) and build from the checkout; Docker's git
  # loader fails on the repository's submodule entry without .gitmodules (binding/go-llama.cpp).
  # ref = commit hash (reproducible, recommended for the paper) or branch name (latest pushed commit).
  local src="$1"
  if [[ "$src" =~ ^(https?://[^#]+)#(.+)$ ]]; then
    local url="${BASH_REMATCH[1]}" ref="${BASH_REMATCH[2]}" target co head
    mkdir -p "$ROOT/.src"
    local git=(docker run --rm -v "$ROOT/.src:/src" alpine/git:latest -c safe.directory='*')
    [ -d "$ROOT/.src/optimusdb/.git" ] || "${git[@]}" clone --no-checkout "$url" /src/optimusdb >&2
    if [[ "$ref" =~ ^[0-9a-fA-F]{7,40}$ ]]; then target="$ref"; else target="origin/$ref"; fi
    "${git[@]}" -C /src/optimusdb fetch origin >&2
    "${git[@]}" -C /src/optimusdb checkout -f --detach "$target" >&2
    "${git[@]}" -C /src/optimusdb clean -fdq >&2
    head=$("${git[@]}" -C /src/optimusdb log -1 --format='%H %s' 2>/dev/null)
    ok "OptimusDB source: $head" >&2
    co="$ROOT/.src/optimusdb"
    if [ -f "$co/app/batch_put.go" ] && [ -f "$co/third_party/go-orbit-db/go.mod" ]; then
      ok "Batched ingestion code found (app/batch_put.go, third_party/go-orbit-db)" >&2
    else
      warn "This commit does NOT contain the batched ingestion code (app/batch_put.go, third_party/go-orbit-db)." >&2
      warn "OptimusDB will load one document at a time. Push the changed code and set OPTIMUSDB_SRC in versions.env." >&2
    fi
    if [ -f "$co/app/group_commit.go" ] && [ -f "$co/app/lineage_queue.go" ]; then
      ok "Performance code found (group commit, field indexes, document cache)" >&2
    else
      warn "This commit does NOT contain the performance changes (app/group_commit.go). Push them before measuring." >&2
    fi
    echo "$co"
  else echo "$src"; fi
}
