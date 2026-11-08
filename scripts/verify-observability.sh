#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
for cluster in karmada-mgmt dc-primary dc-secondary cloud-azure; do
  kubectl --context "kind-$cluster" -n monitoring rollout status deployment/alloy --timeout=90s
  kubectl --context "kind-$cluster" -n monitoring rollout status deployment/kube-state-metrics --timeout=90s
done
kubectl --context kind-karmada-mgmt -n monitoring rollout status deployment/prometheus-server --timeout=90s
kubectl --context kind-karmada-mgmt -n monitoring rollout status statefulset/loki --timeout=90s
kubectl --context kind-karmada-mgmt -n monitoring rollout status deployment/grafana --timeout=90s
kubectl --context kind-karmada-mgmt -n monitoring rollout status deployment/karmada-lab-exporter --timeout=90s
for pvc in prometheus-server storage-loki-0 grafana; do
  kubectl --context kind-karmada-mgmt -n monitoring wait --for=jsonpath='{.status.phase}'=Bound "pvc/$pvc" --timeout=30s
done
curl -fsS http://127.0.0.1:31090/-/ready >/dev/null
curl -fsS http://127.0.0.1:31091/ready >/dev/null
check_metrics() {
  curl -fsSG http://127.0.0.1:31090/api/v1/query \
    --data-urlencode 'query=up{job="prometheus.scrape.kube_state_metrics"}' | python3 -c '
import json, sys
data = json.load(sys.stdin)
if data["status"] != "success": sys.exit("Prometheus query failed")
results = {x["metric"].get("source_cluster"): x["value"][1] for x in data["data"]["result"]}
expected = {"karmada-mgmt", "dc-primary", "dc-secondary", "cloud-azure"}
bad = sorted(cluster for cluster in expected if results.get(cluster) != "1")
if bad: sys.exit("Missing or unhealthy metrics sources: " + ", ".join(bad))
print("Prometheus: all four cluster kube-state-metrics targets healthy")
'
}
ready=0
for attempt in {1..12}; do
  if check_metrics; then ready=1; break; fi
  echo "Waiting for all remote-write sources (attempt $attempt/12)..." >&2
  sleep 5
done
[[ "$ready" -eq 1 ]] || { echo 'Prometheus did not receive healthy metrics from all four clusters.' >&2; exit 1; }
check_cadvisor() {
  curl -fsSG http://127.0.0.1:31090/api/v1/query \
    --data-urlencode 'query=up{job="prometheus.scrape.cadvisor"}' | python3 -c '
import json, sys
data = json.load(sys.stdin)
if data["status"] != "success": sys.exit("Prometheus cAdvisor query failed")
results = {x["metric"].get("source_cluster"): x["value"][1] for x in data["data"]["result"]}
expected = {"karmada-mgmt", "dc-primary", "dc-secondary", "cloud-azure"}
bad = sorted(cluster for cluster in expected if results.get(cluster) != "1")
if bad: sys.exit("Missing or unhealthy cAdvisor sources: " + ", ".join(bad))
print("Prometheus: all four cluster cAdvisor targets healthy")
'
}
ready=0
for attempt in {1..18}; do
  if check_cadvisor; then ready=1; break; fi
  echo "Waiting for all cAdvisor sources (attempt $attempt/18)..." >&2
  sleep 5
done
[[ "$ready" -eq 1 ]] || { echo 'Prometheus did not receive healthy cAdvisor metrics from all four clusters.' >&2; exit 1; }
for metric in container_cpu_usage_seconds_total container_memory_working_set_bytes; do
  curl -fsSG http://127.0.0.1:31090/api/v1/query \
    --data-urlencode "query=count by(source_cluster) (${metric}{job=\"prometheus.scrape.cadvisor\"})" | python3 -c '
import json,sys
data=json.load(sys.stdin)
seen={x["metric"].get("source_cluster") for x in data["data"]["result"]}
expected={"karmada-mgmt", "dc-primary", "dc-secondary", "cloud-azure"}
if data["status"] != "success" or not expected <= seen:
 sys.exit("Missing actual usage series for " + ", ".join(sorted(expected-seen)))
print("Actual container usage series present from all four clusters")
'
done
ready=0
for attempt in {1..12}; do
  if curl -fsSG http://127.0.0.1:31090/api/v1/query \
    --data-urlencode 'query=(karmada_lab_exporter_poll_success == 1) and (time() - karmada_lab_exporter_last_poll_timestamp_seconds < 60)' | \
    python3 -c 'import json,sys; d=json.load(sys.stdin); sys.exit(d.get("status") != "success" or not d["data"]["result"])'; then
    ready=1; break
  fi
  echo "Waiting for healthy, fresh placement exporter metrics (attempt $attempt/12)..." >&2
  sleep 5
done
[[ "$ready" -eq 1 ]] || { echo 'Placement exporter poll failed or its metrics are stale.' >&2; exit 1; }
echo 'Placement exporter: fresh successful Karmada poll'
echo 'Backend and metrics checks passed. Event freshness, annotations and demo data need separate verification.'
