#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
KCFG="${KARMADA_CONFIG:-$PWD/.runtime/karmada/karmada-apiserver.config}"
[[ -f "$KCFG" ]] || { echo "Karmada API kubeconfig missing: $KCFG" >&2; exit 1; }
for c in dc-primary dc-secondary cloud-azure; do
  echo "Checking metrics-server in $c"
  kubectl --context "kind-$c" -n kube-system rollout status deploy/metrics-server --timeout=90s
  kubectl --context "kind-$c" top nodes >/dev/null || {
    echo "metrics-server on $c cannot provide node data" >&2; exit 1;
  }
  kubectl --context "kind-$c" top pods -A >/dev/null || {
    echo "metrics-server on $c cannot provide pod data" >&2; exit 1;
  }
done
kubectl --context kind-karmada-mgmt -n karmada-system rollout status deploy/karmada-metrics-adapter --timeout=120s
kubectl --context kind-karmada-mgmt -n karmada-system rollout status deploy/karmada-controller-manager --timeout=120s
available="$(kubectl --kubeconfig "$KCFG" get apiservice v1beta1.metrics.k8s.io -o jsonpath='{.status.conditions[?(@.type=="Available")].status}')"
[[ "$available" == True ]] || { echo "Karmada metrics APIService is not Available (status=$available)" >&2; exit 1; }
kubectl --kubeconfig "$KCFG" get --raw '/apis/metrics.k8s.io/v1beta1' >/dev/null
for resource in nodes pods; do
  kubectl --kubeconfig "$KCFG" get --raw "/apis/metrics.k8s.io/v1beta1/$resource" | python3 -c '
import json, sys
items = json.load(sys.stdin)["items"]
expected = {"dc-primary", "dc-secondary", "cloud-azure"}
seen = {item.get("metadata", {}).get("annotations", {}).get("resource.karmada.io/query-from-cluster") for item in items}
missing = expected - seen
if missing:
    sys.exit("Aggregated metrics missing clusters: " + ", ".join(sorted(missing)))
print("Aggregated metrics include all three member clusters")
'
done
kubectl --kubeconfig "$KCFG" api-resources --api-group=autoscaling.karmada.io | grep -qi federatedhpa || {
  echo 'FederatedHPA API missing from Karmada' >&2; exit 1;
}
echo 'FederatedHPA prerequisites: metrics-server 3/3, Karmada adapter/APIService and API registration are responsive.'
