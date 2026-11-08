#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p .runtime/kind-owned
chmod 700 .runtime .runtime/kind-owned
for c in karmada-mgmt dc-primary dc-secondary cloud-azure; do
  clusters="$(kind get clusters)"
  if printf '%s\n' "$clusters" | grep -qx "$c"; then
    echo "exists: $c"
  else
    kind create cluster --name "$c" --config "bootstrap/kind/$c.yaml"
    docker inspect -f '{{.Id}}' "${c}-control-plane" > ".runtime/kind-owned/$c.id"
    chmod 600 ".runtime/kind-owned/$c.id"
    if [[ "$c" == karmada-mgmt && -d .runtime/karmada ]]; then
      # A newly created management cluster cannot use the old control-plane
      # kubeconfig or certificates. Preserve them privately for inspection.
      mkdir -p .runtime/archive
      chmod 700 .runtime/archive
      archive="$(mktemp -d .runtime/archive/karmada.XXXXXX)"
      mv .runtime/karmada "$archive/karmada"
      echo "Archived stale management credentials under $archive; FreeLens must import the new Karmada kubeconfig."
    fi
  fi
  kubectl --context "kind-$c" wait --for=condition=Ready nodes --all --timeout=180s
  kubectl --context "kind-$c" get nodes -o wide
 done
# Exports for FreeLens (kind contexts with role names); never commit kubeconfigs.
mkdir -p .runtime/freelens
chmod 700 .runtime .runtime/freelens
for c in karmada-mgmt dc-primary dc-secondary cloud-azure; do
  kind get kubeconfig --name "$c" > ".runtime/freelens/$c.yaml"
  chmod 600 ".runtime/freelens/$c.yaml"
done
