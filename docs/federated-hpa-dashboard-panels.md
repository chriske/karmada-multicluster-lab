# Dashboard updates for FederatedHPA

The existing three JSON dashboards are primarily scheduling-focused; add a fourth group of autoscaling panels to the overview when the live exporter exists:

| Panel | Source | Signal |
|---|---|---|
| Desired replicas | `karmada_lab_desired_replicas` | HPA target set on Karmada Deployment |
| Assigned by member | `karmada_lab_assigned_replicas` | Karmada scheduler binding |
| Available by member | `kube_deployment_status_replicas_available{member_cluster=~"..."}` | member readiness |
| Actual average CPU (%) | FederatedHPA status `currentMetrics` exporter extension (not yet implemented) | resource metric utilization |
| HPA target (%) | FederatedHPA spec resource metric exported by extension | scale policy |
| HPA reconciliation latency | `karmada_federatedhpa_process_duration_seconds_bucket` | Karmada native metrics |
| HPA metric collection latency | `karmada_federatedhpa_pull_metrics_duration_seconds_bucket` | adapter timing |
| Event annotations | Loki `source_type="k8s-event"` and `source_type="scenario-marker"` | Event/experiment timeline |

Add validation that Grafana's Loki datasource with UID `loki` is provisioned, and event JSON parser matches `loki.source.kubernetes_events` actual emitted schema; this is a known not-yet-integrated dependency.

DO NOT use CPU consumption from Prometheus to control FederatedHPA when targeting `Resource` CPU: it reads `metrics.k8s.io` through Karmada metrics adapter. The Prometheus data is purely for visualization in this experiment.
