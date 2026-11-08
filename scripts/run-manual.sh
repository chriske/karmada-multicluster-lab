#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export KARMADA_CONFIG="${KARMADA_CONFIG:-$PWD/.runtime/karmada/karmada-apiserver.config}"
# Avoid HPA fighting manual replica changes.
kubectl --kubeconfig "$KARMADA_CONFIG" -n demo delete federatedhpa placement-demo --ignore-not-found
for replicas in 4 8 10 16 22 8 4; do
  echo "[manual] set desired replicas=$replicas"
  SCENARIO=manual python3 scripts/emit-marker.py "Manual desired replicas = ${replicas}" || true
  kubectl --kubeconfig "$KARMADA_CONFIG" -n demo scale deployment/placement-demo --replicas="$replicas"
  kubectl --kubeconfig "$KARMADA_CONFIG" -n demo get resourcebindings -o wide || true
  # Karmada loop is asynchronous; sufficient for observation, not a pass/fail criterion.
  sleep "${STAGE_SECONDS:-35}"
done
