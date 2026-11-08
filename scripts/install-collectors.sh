#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export HELM_CONFIG_HOME="$PWD/.runtime/helm/config" HELM_CACHE_HOME="$PWD/.runtime/helm/cache" HELM_DATA_HOME="$PWD/.runtime/helm/data"
mkdir -p .runtime/charts .runtime/rendered
if [[ ! -f .runtime/charts/alloy-1.15.0.tgz ]]; then
  helm pull alloy --repo https://grafana.github.io/helm-charts --version 1.15.0 --destination .runtime/charts
fi
if [[ ! -f .runtime/charts/kube-state-metrics-9.0.0.tgz ]]; then
  helm pull oci://ghcr.io/prometheus-community/charts/kube-state-metrics --version 9.0.0 --destination .runtime/charts
fi
printf '%s  %s\n' 2ecc96c05004cc01a45ab23cb390194ad5259ec9d02b42bf148d4468d013aaa3 .runtime/charts/alloy-1.15.0.tgz | sha256sum -c -
printf '%s  %s\n' d187c0990b6e65708280d65b3b371f93f99ef99277fb3d22975d952f110504f6 .runtime/charts/kube-state-metrics-9.0.0.tgz | sha256sum -c -
MGMT_IP="$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' karmada-mgmt-control-plane)"
[[ -n "$MGMT_IP" ]] || { echo 'Cannot determine management Docker node IP.' >&2; exit 1; }
for cluster in karmada-mgmt dc-primary dc-secondary cloud-azure; do
  context="kind-$cluster"
  if [[ "$cluster" == karmada-mgmt ]]; then
    prom=prometheus-server.monitoring.svc:80
    loki=loki.monitoring.svc:3100
    member_label=''
  else
    prom="$MGMT_IP:31090"
    loki="$MGMT_IP:31091"
    member_label=", \"member_cluster\" = \"$cluster\""
  fi
  python3 - "$cluster" "$prom" "$loki" "$member_label" <<'PY'
from pathlib import Path
import sys
cluster, prom, loki, member = sys.argv[1:]
cadvisor_rule = (f'rule {{\n    target_label = "member_cluster"\n    replacement = "{cluster}"\n  }}'
                 if cluster != 'karmada-mgmt' else '')
template = Path('observability/alloy/config.alloy.tmpl').read_text()
for name, value in {'__CLUSTER__': cluster, '__PROM_ENDPOINT__': prom,
                    '__LOKI_ENDPOINT__': loki, '__MEMBER_LABEL__': member,
                    '__CADVISOR_MEMBER_RULE__': cadvisor_rule,
                    '__MGMT_SCRAPES__': (Path('observability/alloy/karmada.alloy').read_text()
                                         if cluster == 'karmada-mgmt' else '')}.items():
    template = template.replace(name, value)
Path(f'.runtime/rendered/alloy-{cluster}.alloy').write_text(template)
PY
  config=".runtime/rendered/alloy-$cluster.alloy"
  helm template kube-state-metrics .runtime/charts/kube-state-metrics-9.0.0.tgz --namespace monitoring > ".runtime/rendered/ksm-$cluster.yaml"
  helm template alloy .runtime/charts/alloy-1.15.0.tgz --namespace monitoring --set controller.type=deployment \
    --set-file "alloy.configMap.content=$config" > ".runtime/rendered/alloy-$cluster.yaml"
  kubectl --context "$context" create namespace monitoring --dry-run=client -o yaml | kubectl --context "$context" apply -f -
  kubectl --context "$context" apply -f observability/alloy/node-proxy-rbac.yaml
  helm --kube-context "$context" upgrade --install kube-state-metrics .runtime/charts/kube-state-metrics-9.0.0.tgz \
    --namespace monitoring --wait --timeout 5m
  helm --kube-context "$context" upgrade --install alloy .runtime/charts/alloy-1.15.0.tgz \
    --namespace monitoring --set controller.type=deployment --set-file "alloy.configMap.content=$config" --wait --timeout 5m
done
echo 'Collectors installed; verify actual remote-write, events, and annotations before declaring success.'
