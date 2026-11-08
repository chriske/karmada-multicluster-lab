#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export KARMADA_CONFIG="${KARMADA_CONFIG:-$PWD/.runtime/karmada/karmada-apiserver.config}"
for c in dc-primary dc-secondary cloud-azure; do
  kubectl --context "kind-$c" apply -f scenarios/loadgen.yaml
  kubectl --context "kind-$c" -n demo scale deploy/cloud-burst-loadgen --replicas=0
  kubectl --context "kind-$c" top pods -n demo >/dev/null || {
    echo "Metrics API not ready in $c; cannot start FederatedHPA experiment"; exit 1;
  }
done
if ! kubectl --kubeconfig "$KARMADA_CONFIG" get --raw /apis/metrics.k8s.io/v1beta1 >/dev/null; then
  echo 'Karmada aggregated metrics API is missing; install karmada-metrics-adapter first'; exit 1
fi
kubectl --kubeconfig "$KARMADA_CONFIG" -n demo scale deployment/placement-demo --replicas=4
kubectl --kubeconfig "$KARMADA_CONFIG" apply -f karmada/federated-hpa.yaml
SCENARIO=auto python3 scripts/emit-marker.py "FederatedHPA enabled: CPU target 50%" || true
# Start with two on-prem load generators; cloud load generator is ready when it gets endpoints.
for c in dc-primary dc-secondary cloud-azure; do
  kubectl --context "kind-$c" -n demo scale deploy/cloud-burst-loadgen --replicas=1
done
SCENARIO=auto python3 scripts/emit-marker.py "Local loadgen enabled in DCs and cloud" || true
cat <<'EOF'
Auto load is now running in each member cluster.
Watch: kubectl --kubeconfig .runtime/karmada/karmada-apiserver.config -n demo get fhpa -w
       kubectl --kubeconfig .runtime/karmada/karmada-apiserver.config -n demo get resourcebinding -w
Stop:  make auto-stop
Tune:  kubectl --context kind-dc-primary -n demo set env deploy/cloud-burst-loadgen LOAD_WORKERS=8
EOF
