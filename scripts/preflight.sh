#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

# Host prerequisites only: no cluster needs to exist yet.
for bin in kind kubectl helm docker karmadactl python3 git make curl openssl; do
  command -v "$bin" >/dev/null || { echo "Missing host tool: $bin. Install host prerequisites first." >&2; exit 1; }
done
check_version() {
  local tool="$1" expected="$2" actual="$3"
  if [[ "$actual" != "$expected" ]]; then
    echo "$tool: expected $expected, found ${actual:-unknown}; run the host tools installer." >&2
    exit 1
  fi
  echo "$tool: $actual"
}
check_version kind v0.33.0 "$(kind version | awk '{print $2}')"
check_version kubectl v1.35.9 "$(kubectl version --client -o json | python3 -c 'import json,sys; print(json.load(sys.stdin)["clientVersion"]["gitVersion"])')"
check_version helm v3.22.1 "$(helm version --short | cut -d+ -f1)"
check_version karmadactl v1.19.1 "$(karmadactl version | sed -n 's/.*GitVersion:"\([^"]*\)".*/\1/p')"
if ! docker info >/dev/null 2>&1; then
  echo 'Docker daemon is unavailable. Check Docker Desktop WSL integration and socket permissions.' >&2
  exit 1
fi
echo 'Docker daemon: reachable'
echo 'Host prerequisites: ready; cluster components are installed by the Kubernetes bootstrap.'
