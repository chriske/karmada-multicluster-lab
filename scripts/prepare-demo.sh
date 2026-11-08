#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export KARMADA_CONFIG="${KARMADA_CONFIG:-$PWD/.runtime/karmada/karmada-apiserver.config}"
hpa="$(kubectl --kubeconfig "$KARMADA_CONFIG" -n demo get federatedhpa placement-demo --ignore-not-found -o name)"
[[ -z "$hpa" ]] || { echo 'FederatedHPA is active; run make reset-demo before reconciling the demo.' >&2; exit 1; }
for c in dc-primary dc-secondary cloud-azure; do
  active="$(kubectl --context "kind-$c" -n demo get deployment cloud-burst-loadgen --ignore-not-found -o jsonpath='{.spec.replicas}')"
  [[ -z "$active" || "$active" == 0 ]] || { echo "Load generator is active in $c; run make reset-demo first." >&2; exit 1; }
done
existing="$(kubectl --kubeconfig "$KARMADA_CONFIG" -n demo get deployment placement-demo --ignore-not-found -o name)"
if [[ -z "$existing" ]]; then
  python3 scripts/calibrate-capacity.py
else
  replicas="$(kubectl --kubeconfig "$KARMADA_CONFIG" -n demo get deployment placement-demo -o jsonpath='{.spec.replicas}')"
  [[ "$replicas" == 4 ]] || { echo "Demo currently requests $replicas replicas; run make reset-demo first." >&2; exit 1; }
  for c in dc-primary dc-secondary cloud-azure; do
    owner="$(kubectl --context "kind-$c" -n karmada-lab-system get pod capacity-reservation -o jsonpath='{.metadata.labels.app}')"
    [[ "$owner" == capacity-reservation ]] || { echo "Unexpected reservation owner in $c." >&2; exit 1; }
    kubectl --context "kind-$c" -n karmada-lab-system wait --for=condition=Ready pod/capacity-reservation --timeout=60s
  done
fi
make build load deploy
mkdir -p .runtime/manual
export MANUAL_SNAPSHOT_LOG="$PWD/.runtime/manual/bootstrap-$(date -u +%Y%m%dT%H%M%SZ).jsonl"
python3 scripts/wait-manual-stage.py 4 7
echo 'Demo workload and baseline verified.'
