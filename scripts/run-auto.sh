#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export KARMADA_CONFIG="${KARMADA_CONFIG:-$PWD/.runtime/karmada/karmada-apiserver.config}"
mkdir -p .runtime/auto
export AUTO_SNAPSHOT_LOG="${AUTO_SNAPSHOT_LOG:-$PWD/.runtime/auto/$(date -u +%Y%m%dT%H%M%SZ).jsonl}"
[[ ! -e "$AUTO_SNAPSHOT_LOG" ]] || { echo "Snapshot log already exists: $AUTO_SNAPSHOT_LOG" >&2; exit 1; }
cleanup_on_failure() {
  status=$?
  trap - EXIT
  if [[ "$status" -ne 0 ]]; then
    echo 'Automatic scenario failed; stopping load and attempting baseline reset.' >&2
    if ! ./scripts/reset-demo.sh; then
      echo 'Automatic reset failed; inspect load generators, FederatedHPA and Deployment immediately.' >&2
    fi
  fi
  exit "$status"
}
trap cleanup_on_failure EXIT
./scripts/verify-fhpa-prereqs.sh
./scripts/reset-demo.sh
for c in dc-primary dc-secondary cloud-azure; do
  kubectl --context "kind-$c" apply -f scenarios/loadgen.yaml
  kubectl --context "kind-$c" -n demo rollout status deployment/cloud-burst-loadgen --timeout=120s
done
kubectl --kubeconfig "$KARMADA_CONFIG" apply -f karmada/federated-hpa.yaml
SCENARIO=auto MARKER_REQUIRED=1 python3 scripts/emit-marker.py 'FederatedHPA enabled: CPU target 50%, bounds 4-22'
for c in dc-primary dc-secondary cloud-azure; do
  kubectl --context "kind-$c" -n demo scale deployment/cloud-burst-loadgen --replicas=1
  kubectl --context "kind-$c" -n demo rollout status deployment/cloud-burst-loadgen --timeout=120s
done
SCENARIO=auto MARKER_REQUIRED=1 python3 scripts/emit-marker.py 'Automatic burst: local load enabled'
python3 scripts/monitor-auto.py burst
SCENARIO=auto MARKER_REQUIRED=1 python3 scripts/emit-marker.py 'Automatic burst: cloud replicas ready'
for c in dc-primary dc-secondary cloud-azure; do
  kubectl --context "kind-$c" -n demo scale deployment/cloud-burst-loadgen --replicas=0
  kubectl --context "kind-$c" -n demo rollout status deployment/cloud-burst-loadgen --timeout=120s
done
SCENARIO=auto MARKER_REQUIRED=1 python3 scripts/emit-marker.py 'Automatic burst: load stopped, waiting for scale-in'
python3 scripts/monitor-auto.py cooldown
SCENARIO=auto MARKER_REQUIRED=1 python3 scripts/emit-marker.py 'Automatic burst: scale-in to four ready'
./scripts/reset-demo.sh
trap - EXIT
echo "Automatic scenario completed; snapshots: $AUTO_SNAPSHOT_LOG"
