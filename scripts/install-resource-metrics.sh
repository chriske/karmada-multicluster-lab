#!/usr/bin/env bash
# Required part of the DEFAULT bootstrap: metrics-server -> Karmada metrics-adapter -> FederatedHPA.
# Uses pinned official manifests/helper. Runtime integration still needs validation on WSL2/kind.
set -euo pipefail
cd "$(dirname "$0")/.."
: "${KARMADA_VERSION:=v1.19.1}"
: "${METRICS_SERVER_VERSION:=v0.8.0}"

for exe in git kubectl; do
  command -v "$exe" >/dev/null || { echo "Required binary not found: $exe" >&2; exit 1; }
done
HOSTCFG="$(realpath .runtime/freelens/karmada-mgmt.yaml)"
KARMADA_CFG="$(realpath .runtime/karmada/karmada-apiserver.config)"
[[ -s "$HOSTCFG" && -s "$KARMADA_CFG" ]] || {
  echo 'Missing management or Karmada kubeconfig; run make kind-up and make karmada-up first.' >&2; exit 1;
}

for c in dc-primary dc-secondary cloud-azure; do
  CTX="kind-$c"
  echo "=== Installing metrics-server ${METRICS_SERVER_VERSION} into ${c} ==="
  kubectl --context "$CTX" apply -f "https://github.com/kubernetes-sigs/metrics-server/releases/download/${METRICS_SERVER_VERSION}/components.yaml"
  # kind's node kubelet serving certificate is usually not trusted by metrics-server.
  # Do not duplicate the flag on repeated runs.
  args="$(kubectl --context "$CTX" -n kube-system get deployment metrics-server -o jsonpath='{.spec.template.spec.containers[0].args[*]}')"
  if [[ " $args " != *' --kubelet-insecure-tls '* ]]; then
    kubectl --context "$CTX" -n kube-system patch deployment metrics-server --type=json \
      -p='[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'
  fi
  kubectl --context "$CTX" -n kube-system rollout status deployment/metrics-server --timeout=180s
  ok=0
  for try in $(seq 1 30); do
    if kubectl --context "$CTX" top nodes >/dev/null 2>&1; then ok=1; break; fi
    sleep 5
  done
  [[ "$ok" -eq 1 ]] || { echo "metrics.k8s.io not usable in ${c}; inspect metrics-server pod logs and kubelet connectivity" >&2; exit 1; }
  echo "metrics-server API: ready in ${c}"
done

echo '=== Installing the Karmada metrics adapter using pinned official source ==='
SRC="$(realpath -m .runtime/karmada-source)"
if [[ ! -d "$SRC/.git" ]]; then
  git clone --depth 1 --branch "$KARMADA_VERSION" https://github.com/karmada-io/karmada.git "$SRC"
fi
actual="$(git -C "$SRC" describe --tags --exact-match 2>/dev/null || true)"
[[ "$actual" == "$KARMADA_VERSION" ]] || {
  echo "Pinned Karmada source must be ${KARMADA_VERSION}, found '${actual:-unknown}'. Fix ${SRC}." >&2; exit 1;
}
CTX="$(kubectl --kubeconfig "$KARMADA_CFG" config current-context)"
[[ -n "$CTX" ]] || { echo 'No Karmada API kubeconfig context' >&2; exit 1; }
(
  cd "$SRC"
  bash hack/deploy-metrics-adapter.sh "$HOSTCFG" kind-karmada-mgmt "$KARMADA_CFG" "$CTX"
)
"$(dirname "$0")/verify-fhpa-prereqs.sh"
