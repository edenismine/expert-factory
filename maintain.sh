#!/usr/bin/env bash
# Refresh compiled experts: pull upstream, rebuild the graph, restart the server.
#
#   ./maintain.sh status            what each expert serves vs upstream
#   ./maintain.sh refresh [name]    pull + AST-only graph update (no API cost)
#   ./maintain.sh refresh name --deep   full semantic re-extraction (costs tokens)
#
# Runs on the host, using the full graphify toolchain. The MCP containers only
# serve; they never extract.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXPERTS="$ROOT/experts"

die() { echo "error: $*" >&2; exit 1; }

command -v graphify >/dev/null || die "graphify not on PATH (needed to rebuild graphs)"

expert_names() {
  find "$EXPERTS" -mindepth 2 -maxdepth 2 -name expert.json -exec dirname {} \; 2>/dev/null \
    | xargs -I{} basename {} | sort
}

graph_commit() {
  # built_at_commit is the last key in graph.json; tail avoids parsing 20MB+.
  tail -c 4096 "$1" 2>/dev/null | sed -n 's/.*"built_at_commit": *"\([0-9a-f]*\)".*/\1/p' | tail -1
}

# The commit the graph was last *reconciled* against, which is not always the
# commit stamped inside graph.json: graphify leaves outputs untouched when a pull
# changes no topology, so the stamp can legitimately trail HEAD.
synced_commit() { cat "$1/synced_at" 2>/dev/null || true; }

refresh_one() {
  local name="$1" deep="$2"
  local home="$EXPERTS/$name" repo="$EXPERTS/$name/repo" graph="$EXPERTS/$name/graph"
  [ -f "$home/expert.json" ] || die "unknown expert: $name"

  echo "== $name"

  # The graph lives outside the checkout, so a clean tree is the norm here.
  # Anything else means unexpected local edits: stop rather than discard them.
  local dirty
  dirty="$(git -C "$repo" status --porcelain)"
  if [ -n "$dirty" ]; then
    echo "$dirty" | sed 's/^/   /'
    die "$name checkout has local changes; resolve them before refreshing"
  fi

  local before after
  before="$(git -C "$repo" rev-parse HEAD)"
  git -C "$repo" fetch --quiet origin
  git -C "$repo" merge --ff-only --quiet FETCH_HEAD 2>/dev/null \
    || die "$name cannot fast-forward; upstream history diverged"
  after="$(git -C "$repo" rev-parse HEAD)"

  if [ "$before" = "$after" ] && [ "$(synced_commit "$graph")" = "$after" ] && [ "$deep" != "1" ]; then
    echo "   up to date at ${after:0:7}"
    return
  fi

  if [ "$before" != "$after" ]; then
    echo "   pulled ${before:0:7} -> ${after:0:7} ($(git -C "$repo" rev-list --count "$before..$after") commits)"
  fi

  # Run from inside the checkout: graphify stamps built_at_commit from `git
  # rev-parse HEAD` in its own cwd, not in the directory it was pointed at.
  if [ "$deep" = "1" ]; then
    echo "   semantic re-extraction (LLM)"
    (cd "$repo" && GRAPHIFY_OUT="$graph" graphify extract "$repo" --force)
  else
    echo "   updating graph (AST only)"
    (cd "$repo" && GRAPHIFY_OUT="$graph" graphify update "$repo")
  fi

  printf '%s\n' "$after" > "$graph/synced_at"
  # Counts and commit are baked into the skill prose, so they go stale on rebuild.
  "$ROOT/compile.py" sync "$name" | sed 's/^/   /'

  # The server rechecks graph.json's mtime per call, so a restart is not required
  # for correctness — but it drops the old graph from memory promptly.
  if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "expert-$name"; then
    docker restart "expert-$name" >/dev/null && echo "   restarted expert-$name"
  fi

  local rebuilt
  rebuilt="$(graph_commit "$graph/graph.json")"
  if [ "$rebuilt" = "$after" ]; then
    echo "   now at ${after:0:7}"
  else
    echo "   reconciled at ${after:0:7} (no topology change; graph still stamped ${rebuilt:0:7})"
  fi
}

cmd_status() {
  local any=0
  for name in $(expert_names); do
    any=1
    local repo="$EXPERTS/$name/repo" graph="$EXPERTS/$name/graph"
    local head synced behind state
    head="$(git -C "$repo" rev-parse HEAD 2>/dev/null || echo unknown)"
    synced="$(synced_commit "$graph")"
    git -C "$repo" fetch --quiet origin 2>/dev/null || true
    behind="$(git -C "$repo" rev-list --count HEAD..FETCH_HEAD 2>/dev/null || echo '?')"

    if [ "$synced" != "$head" ]; then
      state="needs refresh (graph at ${synced:0:7}${synced:+, }head ${head:0:7})"
    elif [ "$behind" != "0" ] && [ "$behind" != "?" ]; then
      state="$behind commit(s) behind upstream"
    else
      state="current"
    fi

    local running="stopped"
    docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "expert-$name" && running="running"
    printf '%-16s %-9s %-10s %s\n' "$name" "$running" "${head:0:7}" "$state"
  done
  [ "$any" = "1" ] || echo "no experts compiled yet"
}

main() {
  local cmd="${1:-status}"; shift || true
  case "$cmd" in
    status) cmd_status ;;
    refresh)
      # Space-joined rather than an array: macOS ships bash 3.2, which lacks
      # mapfile and errors on empty-array expansion under `set -u`.
      local deep=0 targets=""
      for arg in "$@"; do
        case "$arg" in
          --deep) deep=1 ;;
          -*) die "unknown flag: $arg" ;;
          *) targets="$targets $arg" ;;
        esac
      done
      [ -n "$targets" ] || targets="$(expert_names)"
      [ -n "$targets" ] || die "no experts to refresh"
      for name in $targets; do refresh_one "$name" "$deep"; done
      ;;
    *) die "usage: maintain.sh {status|refresh [name] [--deep]}" ;;
  esac
}

main "$@"
