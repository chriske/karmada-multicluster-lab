# Acceptance tests — executable evidence, not assumptions

This is the acceptance checklist; observed runs, failures and limits are recorded in [VALIDATION_RESULTS.md](VALIDATION_RESULTS.md), not inferred from this table. The user currently defers Windows-host telemetry.

Statuses: `PASS`, `FAIL`, `BLOCKED (no host access)`, `NOT RUN`. Attach exact commands and abbreviated output in `docs/VALIDATION_RESULTS.md`.

| ID | Critical acceptance criterion | How to verify |
|---|---|---|
| A01 | Exactly 4 kind clusters, fixed role names; 3 Push-registered Karmada members, all Ready | `kind get clusters`; `kubectl --kubeconfig .runtime/karmada/karmada-apiserver.config get clusters -o wide` |
| A02 | Windows/FreeLens kubeconfig for 4 clusters plus Karmada API, localhost ports and trusted certificates | Import each `.runtime/freelens/*.yaml` and virtual Karmada kubeconfig, `kubectl get nodes`, inspect Windows FreeLens |
| A03 | All 3 member metrics-server Deployments healthy | Each: `kubectl --context kind-dc-primary top nodes` etc.; `kubectl get apiservice v1beta1.metrics.k8s.io` |
| A04 | Karmada metrics adapter automatically installed and Ready, APIService Available | `kubectl --context kind-karmada-mgmt -n karmada-system get deploy karmada-metrics-adapter`; `kubectl --kubeconfig ... get apiservice v1beta1.metrics.k8s.io`; Karmada `get --raw /apis/metrics.k8s.io/v1beta1` |
| A05 | FederatedHPA API/controller present before automatic demo | Karmada `kubectl api-resources | grep -i federated`; create/delete a test FHPA or inspect reconciled FHPA in demo |
| A06 | Kind mgmt has bound PVCs for Prometheus 5Gi, Loki 3Gi, Grafana 1Gi; retention 24h | `kubectl --context kind-karmada-mgmt -n monitoring get pvc,pods`; inspect effective Prometheus flags/Loki runtime config |
| A07 | Metrics enter centralized Prometheus from all four logical sources | PromQL `up` grouped by source; inspect meaningful series from each cluster and Karmada |
| A08 | Loki receives cluster Events and scenario markers; Grafana annotations enabled on all 3 dashboards | Generate a **real** Warning/Normal Event (appropriate local test) and scenario marker; query Loki; view annotations in Grafana |
| A09 | Management NodePorts 31090 & 31091 accessible from pod in EACH member, no FreeLens port-forward required for telemetry | `kubectl --context kind-<member> run ... curl` or equivalent; verify health/remote write |
| A10 | Grafana JSON dashboards provisioned, load with datasource UID and useful data, not just empty panels | Grafana API/dashboard UI checks, scrape comparisons, screenshot if possible |
| A11 | Manual burst produces measurable cloud overflow as on-prem requests fill | Record 4→8→10→16→22 replikas, ResourceBinding assigned counts, member `Deployment.status.availableReplicas`, corresponding annotations |
| A12 | Manual scale down to baseline without HPA conflict | Verify FHPA absent and loadgenerators scaled to zero; final desired/Ready and binding status |
| A13 | Auto burst triggered from CPU utilization via FederatedHPA; no manual replica writer | Federation metrics API valid, FHPA desiredReplicas increases, cloud assigned/ready replicas appear, timeline and CPU rise coincide |
| A14 | Auto scale-in after stopping loadgen | Desired replicas decrease toward min4 after stabilization and health; record observed duration rather than promising exact time |
| A15 | Host resources stable within 20GiB WSL limit; cleanup works; secure config handling | Verify no OOM, service bind only intended loopback host ports, no credentials in Git, `make down` and recreation |
| A16 | Reproducible `make up`, `make verify`, `make demo-manual`, `make demo-auto`, `make reset-demo`, `make down` | Run twice as appropriate; idempotence and structured error output |
| A17 | No old ambiguous member names in project code/config/docs; Karmada objects use role names | `make verify-names` and inspect manifests/kubeconfigs; exclude vendor-generated `kind-` context prefix rule |

## Test discipline

- Syntax/unit tests run on any machine with Python/Bash. Real Kubernetes/WSL/FreeLens tests only after access is available.
- Do not declare A04 passed merely because the adapter pod exists: aggregated metrics API needs to work end-to-end.
- Do not declare A11/A13 passed on Karmada *assigned* counts alone: member Ready replicas and cloud overflow must be observed.
- If Karmada fails to automatically reclaim running cloud replicas on scale-in, record actual behavior accurately; an explicit rebalance scenario can be added later.
- HPA and observability dependencies are mandatory bootstrap components even when the manual scenario is chosen first.
