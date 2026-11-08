#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export KARMADA_CONFIG="${KARMADA_CONFIG:-$PWD/.runtime/karmada/karmada-apiserver.config}"
python3 scripts/check_cluster_names.py
for c in karmada-mgmt dc-primary dc-secondary cloud-azure; do
  kubectl --context "kind-$c" wait --for=condition=Ready nodes --all --timeout=90s
done
kubectl --kubeconfig "$KARMADA_CONFIG" get clusters -o json | python3 -c '
import json,sys
items=json.load(sys.stdin)["items"]
expected={"dc-primary", "dc-secondary", "cloud-azure"}
members={x["metadata"]["name"]: x for x in items}
if set(members) != expected: sys.exit("Karmada members differ from the three expected clusters")
for name,item in members.items():
 if item.get("spec",{}).get("syncMode") != "Push" or not any(x.get("type")=="Ready" and x.get("status")=="True" for x in item.get("status",{}).get("conditions",[])):
  sys.exit(name + " is not Push/Ready")
print("Karmada: all three members are Push/Ready")
'
./scripts/verify-fhpa-prereqs.sh
./scripts/verify-observability.sh
for c in dc-primary dc-secondary cloud-azure; do
  kubectl --context "kind-$c" -n demo get service placement-demo >/dev/null
done
desired="$(kubectl --kubeconfig "$KARMADA_CONFIG" -n demo get deployment placement-demo -o jsonpath='{.spec.replicas}')"
[[ "$desired" =~ ^[0-9]+$ ]] || { echo 'Cannot determine demo desired replicas.' >&2; exit 1; }
mkdir -p .runtime/manual
export MANUAL_SNAPSHOT_LOG="$PWD/.runtime/manual/verify-$(date -u +%Y%m%dT%H%M%SZ).jsonl"
python3 scripts/wait-manual-stage.py "$desired" 7
python3 scripts/verify-telemetry.py
echo 'Current lab health checks passed. Scenario behavior and fresh-install reproducibility are separate tests.'
