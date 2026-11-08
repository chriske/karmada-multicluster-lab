#!/usr/bin/env bash
# Install only the central backends. Collection and end-to-end checks are separate.
set -euo pipefail
cd "$(dirname "$0")/.."
export HELM_CONFIG_HOME="$PWD/.runtime/helm/config"
export HELM_CACHE_HOME="$PWD/.runtime/helm/cache"
export HELM_DATA_HOME="$PWD/.runtime/helm/data"
mkdir -p .runtime/charts .runtime/rendered
fetch_chart() {
  local name="$1" version="$2" source="$3" sha="$4"
  local file=".runtime/charts/${name}-${version}.tgz"
  if [[ ! -f "$file" ]]; then
    helm pull "$source" --version "$version" --destination .runtime/charts
  fi
  printf '%s  %s\n' "$sha" "$file" | sha256sum -c -
}
fetch_chart prometheus 29.45.1 oci://ghcr.io/prometheus-community/charts/prometheus 33e4585307a61f464993ae9aac0d4430865e0fcba16a9e13ba199beb63eeb1fb
fetch_chart loki 21.0.0 oci://ghcr.io/grafana-community/helm-charts/loki 33e18ba4148a352581ca48c99c9df754ba6776f00c2ea41bab3e59e22c76b151
fetch_chart grafana 14.4.0 oci://ghcr.io/grafana-community/helm-charts/grafana bfba0d92aa35f10aebc73368167308d563558693e0a7665d31fe92f59f186738
CTX=kind-karmada-mgmt
dashboard_hash="$(sha256sum observability/grafana/*.json | sha256sum | awk '{print $1}')"
for chart in prometheus loki grafana; do
  case "$chart" in
    prometheus) version=29.45.1 ;;
    loki) version=21.0.0 ;;
    grafana) version=14.4.0 ;;
  esac
  extra=()
  if [[ "$chart" == grafana ]]; then extra=(--set-string "podAnnotations.karmada-lab\\.io/dashboard-hash=$dashboard_hash"); fi
  helm template "$chart" ".runtime/charts/$chart-$version.tgz" --namespace monitoring \
    -f "observability/helm-values/$chart.yaml" "${extra[@]}" > ".runtime/rendered/$chart.yaml"
done
kubectl --context "$CTX" create namespace monitoring --dry-run=client -o yaml | kubectl --context "$CTX" apply -f -
kubectl --context "$CTX" -n monitoring create configmap karmada-lab-dashboards \
  --from-file=observability/grafana --dry-run=client -o yaml | kubectl --context "$CTX" apply -f -
for chart in prometheus loki grafana; do
  case "$chart" in
    prometheus) version=29.45.1 ;;
    loki) version=21.0.0 ;;
    grafana) version=14.4.0 ;;
  esac
  extra=()
  if [[ "$chart" == grafana ]]; then extra=(--set-string "podAnnotations.karmada-lab\\.io/dashboard-hash=$dashboard_hash"); fi
  helm --kube-context "$CTX" upgrade --install "$chart" ".runtime/charts/$chart-$version.tgz" \
    --namespace monitoring -f "observability/helm-values/$chart.yaml" "${extra[@]}" --wait --timeout 8m
done
kubectl --context "$CTX" apply -f observability/network/nodeports.yaml
kubectl --context "$CTX" -n monitoring get pvc,pods,svc
echo 'Central backends installed. Alloy collection and end-to-end verification are not yet complete.'
