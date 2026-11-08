#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
for c in dc-primary dc-secondary cloud-azure; do
  kubectl --context "kind-$c" -n demo scale deploy/cloud-burst-loadgen --replicas=0 || true
done
KARMADA_CONFIG="${KARMADA_CONFIG:-$PWD/.runtime/karmada/karmada-apiserver.config}"
kubectl --kubeconfig "$KARMADA_CONFIG" -n demo delete federatedhpa placement-demo --ignore-not-found

SCENARIO=auto python3 scripts/emit-marker.py "FederatedHPA disabled and load stopped" || true
