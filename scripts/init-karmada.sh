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
if [[ -f "$KARMADA_CFG" ]]; then
  # init writes its kubeconfig before installing all components. A file left by
  # a failed init must never be mistaken for a completed installation.
  # The Docker node IP is reachable by pods, but not necessarily by the WSL
  # host with Docker Desktop. Use the explicitly mapped loopback port there.
  kubectl config view --kubeconfig "$KARMADA_CFG" --raw --flatten > .runtime/karmada/karmada-freelens.yaml
  CTX="$(kubectl config current-context --kubeconfig "$KARMADA_CFG")"
  CLUSTER="$(kubectl --kubeconfig "$KARMADA_CFG" config view -o jsonpath='{.contexts[?(@.name=="'"$CTX"'")].context.cluster}')"
  kubectl --kubeconfig .runtime/karmada/karmada-freelens.yaml config set-cluster "$CLUSTER" --server=https://127.0.0.1:16447 >/dev/null
  chmod 600 .runtime/karmada/karmada-freelens.yaml
  if ! kubectl --kubeconfig .runtime/karmada/karmada-freelens.yaml --request-timeout=5s get crd federatedhpas.autoscaling.karmada.io >/dev/null; then
    echo 'Existing Karmada kubeconfig does not point to a fully initialized API. Diagnose the partial installation before retrying; it will not be overwritten.' >&2
    exit 1
  fi
else
  # karmadactl couples its client port to the NodePort. Docker Desktop only
  # publishes that NodePort on host port 16447, so bridge the two locally
  # during init; the relay never listens on an external interface.
  python3 scripts/init-api-relay.py &
  relay_pid=$!
  trap 'kill "$relay_pid" 2>/dev/null; wait "$relay_pid" 2>/dev/null' EXIT
  sleep 1
  if ! kill -0 "$relay_pid" 2>/dev/null; then
    echo 'Cannot start temporary loopback relay on port 32443; check whether that port is already in use.' >&2
    exit 1
  fi
  extra_ca_args=()
  if [[ -n "${KARMADA_CA_CERT:-}" || -n "${KARMADA_CA_KEY:-}" ]]; then
    [[ -n "${KARMADA_CA_CERT:-}" && -n "${KARMADA_CA_KEY:-}" ]] || { echo 'Both KARMADA_CA_CERT and KARMADA_CA_KEY must be set.' >&2; exit 1; }
    extra_ca_args=(--ca-cert-file "$KARMADA_CA_CERT" --ca-key-file "$KARMADA_CA_KEY")
  fi
  karmadactl --kubeconfig "$HOSTCFG" --context kind-karmada-mgmt init \
    --crds "https://github.com/karmada-io/karmada/releases/download/${KARMADA_VERSION}/crds.tar.gz" \
    --karmada-data "$(realpath .runtime/karmada)" \
    --karmada-pki "$(realpath .runtime/karmada)/pki" \
    --cert-external-ip "127.0.0.1,${MGMT_IP}" \
    --karmada-apiserver-advertise-address 127.0.0.1 \
    --kube-image-tag v1.36.2 \
    "${extra_ca_args[@]}" \
    --port 32443
  kill "$relay_pid"
  wait "$relay_pid" 2>/dev/null || :
  trap - EXIT
fi
# Host-side tools use the mapped loopback port. In-cluster controllers receive
# their own kubeconfigs from karmadactl and use the management Service DNS.
CTX="$(kubectl config current-context --kubeconfig "$KARMADA_CFG")"
CLUSTER="$(kubectl --kubeconfig "$KARMADA_CFG" config view -o jsonpath='{.contexts[?(@.name=="'"$CTX"'")].context.cluster}')"
kubectl --kubeconfig "$KARMADA_CFG" config set-cluster "$CLUSTER" --server=https://127.0.0.1:16447 >/dev/null
kubectl config view --kubeconfig "$KARMADA_CFG" --raw --flatten > .runtime/karmada/karmada-freelens.yaml
chmod 600 .runtime/karmada/*config* .runtime/karmada/karmada-freelens.yaml
# Default resource-model buckets coarsen free capacity and hide individual
# 250m slots. This lab calibrates against the exact Cluster resource summary.
python3 scripts/configure-scheduler.py
for component in karmada-apiserver karmada-aggregated-apiserver kube-controller-manager karmada-scheduler karmada-controller-manager karmada-webhook; do
  kubectl --kubeconfig "$HOSTCFG" --context kind-karmada-mgmt -n karmada-system rollout status "deployment/$component" --timeout=180s
done
# For federation, in-cluster clients require routable member API addresses.
for c in dc-primary dc-secondary cloud-azure; do
  IP="$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "${c}-control-plane")"
  INTERNAL="$(realpath .runtime/karmada/${c}-internal.yaml)"
  kind get kubeconfig --name "$c" > "$INTERNAL"
  kubectl --kubeconfig "$INTERNAL" config set-cluster "kind-$c" --server="https://${IP}:6443" >/dev/null
  chmod 600 "$INTERNAL"
  # Join contacts the member from the WSL host, so use kind's mapped API.
  # Then advertise the Docker-network endpoint to Karmada's in-cluster clients.
  existing="$(kubectl --kubeconfig "$KARMADA_CFG" get cluster "$c" --ignore-not-found -o name)"
  if [[ -z "$existing" ]]; then
    karmadactl --kubeconfig "$KARMADA_CFG" join "$c" \
      --cluster-kubeconfig "$(realpath ".runtime/freelens/$c.yaml")" --cluster-context "kind-$c"
  fi
  kubectl --kubeconfig "$KARMADA_CFG" patch cluster "$c" --type merge -p "{\"spec\":{\"apiEndpoint\":\"https://${IP}:6443\"}}"
  kubectl --kubeconfig "$KARMADA_CFG" wait --for=condition=Ready "cluster/$c" --timeout=180s
done
kubectl --kubeconfig "$KARMADA_CFG" get clusters
