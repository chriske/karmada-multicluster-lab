# Dashboard updates for FederatedHPA

The Hybrid Cloud Overview includes the following autoscaling and placement signals:

| Panel | Source | Signal |
|---|---|---|
| Desired replicas | `karmada_lab_desired_replicas` | Current Karmada Deployment target; set by the user in the manual demo or by HPA in the auto demo |
| Assigned by member | `karmada_lab_assigned_replicas` | Karmada scheduler binding |
| Available by member | `kube_deployment_status_replicas_available{member_cluster=~"..."}` | member readiness |
| Actual average CPU (%) | FederatedHPA status `currentMetrics` via the placement exporter | resource metric utilization |
| HPA target (%) | FederatedHPA spec resource metric via the placement exporter | scale policy |
| Event annotations | Loki `source_type="k8s-event"` and `source_type="scenario-marker"` | Event/experiment timeline |

The `loki` datasource and annotation definitions are checked by `make verify`; fresh events and scenario markers are queried from Loki. A Kubernetes Warning annotation was also confirmed visually by the user. The HPA activity signal is zero when no HPA exists; its CPU and replica status are unavailable rather than zero in that state.

DO NOT use CPU consumption from Prometheus to control FederatedHPA when targeting `Resource` CPU: it reads `metrics.k8s.io` through Karmada metrics adapter. The Prometheus data is purely for visualization in this experiment.
