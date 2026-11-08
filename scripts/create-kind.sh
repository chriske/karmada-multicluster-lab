#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
for c in karmada-mgmt dc-primary dc-secondary cloud-azure; do
  if kind get clusters | grep -qx "$c"; then
    echo "exists: $c"
  else
    kind create cluster --name "$c" --config "bootstrap/kind/$c.yaml"
  fi
  kubectl --context "kind-$c" get nodes -o wide
 done
# Exports for FreeLens (kind contexts with role names); never commit kubeconfigs.
mkdir -p .runtime/freelens
chmod 700 .runtime .runtime/freelens
for c in karmada-mgmt dc-primary dc-secondary cloud-azure; do
  kind get kubeconfig --name "$c" > ".runtime/freelens/$c.yaml"
  chmod 600 ".runtime/freelens/$c.yaml"
done
