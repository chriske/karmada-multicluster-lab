#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export KARMADA_CONFIG="${KARMADA_CONFIG:-$PWD/.runtime/karmada/karmada-apiserver.config}"
kubectl --kubeconfig "$KARMADA_CONFIG" -n demo get deployment placement-demo >/dev/null
kubectl --kubeconfig "$KARMADA_CONFIG" -n demo delete federatedhpa placement-demo --ignore-not-found --wait=true
for c in dc-primary dc-secondary cloud-azure; do
  found="$(kubectl --context "kind-$c" -n demo get deployment cloud-burst-loadgen --ignore-not-found -o name)"
  if [[ -n "$found" ]]; then
    kubectl --context "kind-$c" -n demo scale deployment/cloud-burst-loadgen --replicas=0
    kubectl --context "kind-$c" -n demo rollout status deployment/cloud-burst-loadgen --timeout=120s
  fi
done
kubectl --kubeconfig "$KARMADA_CONFIG" -n demo scale deployment/placement-demo --replicas=4
mkdir -p .runtime/manual
export MANUAL_SNAPSHOT_LOG="${MANUAL_SNAPSHOT_LOG:-$PWD/.runtime/manual/reset-$(date -u +%Y%m%dT%H%M%SZ).jsonl}"
python3 scripts/wait-manual-stage.py 4 7
SCENARIO=manual MARKER_REQUIRED=1 python3 scripts/emit-marker.py 'Demo reset: 4 replicas ready, HPA and load stopped'
