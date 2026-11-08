#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export KARMADA_CONFIG="${KARMADA_CONFIG:-$PWD/.runtime/karmada/karmada-apiserver.config}"
mkdir -p .runtime/manual
export MANUAL_SNAPSHOT_LOG="${MANUAL_SNAPSHOT_LOG:-$PWD/.runtime/manual/$(date -u +%Y%m%dT%H%M%SZ).jsonl}"
[[ ! -e "$MANUAL_SNAPSHOT_LOG" ]] || { echo "Snapshot log already exists: $MANUAL_SNAPSHOT_LOG" >&2; exit 1; }
kubectl --kubeconfig "$KARMADA_CONFIG" -n demo delete federatedhpa placement-demo --ignore-not-found --wait=true
for c in dc-primary dc-secondary cloud-azure; do
  found="$(kubectl --context "kind-$c" -n demo get deployment cloud-burst-loadgen --ignore-not-found -o name)"
  if [[ -n "$found" ]]; then
    kubectl --context "kind-$c" -n demo scale deployment/cloud-burst-loadgen --replicas=0
    kubectl --context "kind-$c" -n demo rollout status deployment/cloud-burst-loadgen --timeout=120s
  fi
done
stage=0
stage_seconds="${STAGE_SECONDS:-20}"
for replicas in 4 8 10 16 22 8 4; do
  stage=$((stage + 1))
  echo "[manual] stage $stage: desired replicas=$replicas"
  SCENARIO=manual MARKER_REQUIRED=1 python3 scripts/emit-marker.py "Manual stage ${stage}: desired ${replicas}"
  kubectl --kubeconfig "$KARMADA_CONFIG" -n demo scale deployment/placement-demo --replicas="$replicas"
  python3 scripts/wait-manual-stage.py "$replicas" "$stage"
  SCENARIO=manual MARKER_REQUIRED=1 python3 scripts/emit-marker.py "Manual stage ${stage}: ${replicas} replicas ready"
  if [[ "$stage_seconds" != 0 ]]; then sleep "$stage_seconds"; fi
done
echo "Manual scenario completed; snapshots: $MANUAL_SNAPSHOT_LOG"
