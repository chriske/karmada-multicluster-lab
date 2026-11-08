#!/usr/bin/env bash
# Tested only for syntax; requires WSL2 with running kind and karmadactl v1.19.1.
set -euo pipefail
cd "$(dirname "$0")/.."
: "${KARMADA_VERSION:=v1.19.1}"
command -v karmadactl >/dev/null || { echo 'Install matching karmadactl v1.19.1 first'; exit 1; }
mkdir -p .runtime/karmada
chmod 700 .runtime/karmada
HOSTCFG="$(realpath .runtime/freelens/karmada-mgmt.yaml)"
KARMADA_CFG="$(realpath .runtime/karmada/karmada-apiserver.config)"
MGMT_IP="$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' karmada-mgmt-control-plane)"
if [[ ! -f "$KARMADA_CFG" ]]; then
  karmadactl --kubeconfig "$HOSTCFG" --context kind-karmada-mgmt init \
    --crds "https://github.com/karmada-io/karmada/releases/download/${KARMADA_VERSION}/crds.tar.gz" \
    --karmada-data "$(realpath .runtime/karmada)" \
    --karmada-pki "$(realpath .runtime/karmada)/pki" \
    --cert-external-ip "127.0.0.1,${MGMT_IP}" \
    --port 32443
fi
# This second kubeconfig is for user-side management/FreeLens; the original is kept intact
# so controllers and setup scripts can address the API over the Docker network.
kubectl config view --kubeconfig "$KARMADA_CFG" --raw --flatten > .runtime/karmada/karmada-freelens.yaml
CTX="$(kubectl config current-context --kubeconfig "$KARMADA_CFG")"
CLUSTER="$(kubectl --kubeconfig "$KARMADA_CFG" config view -o jsonpath='{.contexts[?(@.name=="'"$CTX"'")].context.cluster}')"
kubectl --kubeconfig .runtime/karmada/karmada-freelens.yaml config set-cluster "$CLUSTER" --server=https://127.0.0.1:16447 >/dev/null
chmod 600 .runtime/karmada/*config* .runtime/karmada/karmada-freelens.yaml
# For federation, in-cluster clients require routable member API addresses.
for c in dc-primary dc-secondary cloud-azure; do
  IP="$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "${c}-control-plane")"
  INTERNAL="$(realpath .runtime/karmada/${c}-internal.yaml)"
  kind get kubeconfig --name "$c" > "$INTERNAL"
  kubectl --kubeconfig "$INTERNAL" config set-cluster "kind-$c" --server="https://${IP}:6443" >/dev/null
  chmod 600 "$INTERNAL"
  # Join only when missing; need member server IP reachable from mgmt Pods.
  if ! kubectl --kubeconfig "$KARMADA_CFG" get cluster "$c" >/dev/null 2>&1; then
    karmadactl --kubeconfig "$KARMADA_CFG" join "$c" \
      --cluster-kubeconfig "$INTERNAL" --cluster-context "kind-$c"
  fi
done
kubectl --kubeconfig "$KARMADA_CFG" get clusters
