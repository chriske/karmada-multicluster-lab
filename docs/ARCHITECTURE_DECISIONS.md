# Architecture decisions — locked for lab v1

| Topic | Decision | Why |
|---|---|---|
| Cluster topology | 4 single-node kind: `karmada-mgmt`, `dc-primary`, `dc-secondary`, `cloud-azure` | Small local simulation, explicit roles |
| Environment | Win11 + WSL2 Ubuntu, Docker Desktop, FreeLens Windows | Familiar native development / direct CLI access |
| Karmada | v1.19.1, 3 Push cluster registrations | Pin and simplify the initial communication model |
| Scheduling | PropagationPolicy with `clusterAffinities`/`overflowAffinities`, `Divided`, dynamic `AvailableReplicas` | On-prem first, then simulated Azure overflow |
| Scenarios | Manual, then CPU-based FederatedHPA | Separate pure scheduling from autoscaling input |
| Metrics API | `metrics-server` in each of 3 members, `karmada-metrics-adapter` in mgmt, aggregated metrics API | Required for Karmada FederatedHPA; Prometheus and Alloy do not replace these |
| Metrics collection | Per-cluster Alloy and kube-state-metrics, central Prometheus | Shared telemetry identity, strong PromQL support |
| Events | Alloy Kubernetes Events → central Loki, default Grafana annotations | Visible policy, scheduling and K8s activity |
| Control-plane state | Karmada state exporter (binding assigned replicas + observed member replica state); scenario marker log events | Expose decisions independently from actual pods |
| Retention/storage | Prometheus 24h 5GiB PVC; Loki 24h 3GiB PVC; Grafana 1GiB PVC | Minimal local retention; no data persistence across kind deletion guaranteed |
| Network | No ingress; NodePorts 31090/31091 + `extraPortMappings`, FreeLens port-forward for UI | Keep infrastructure simple |
| Host metrics | If needed run dedicated Alloy process in WSL, optionally Windows Alloy; do not call container metrics 'whole host' | Prevent misleading resource diagnostics |
| Service distribution | Propagate local ClusterIP Service to all three members separately from Deployment overflow policy | A local-only loadgen per member; no cross-cluster Service/mesh |
| Scale-in/rebalance | Observe actual policy behavior; don't promise automatic move-back for already-running replicas | Distinguish desired outcome from Karmada guarantees |

## Fixed naming and ports

| Logical name | kind context | Kubernetes API, Windows loopback |
|---|---|---|
| `karmada-mgmt` | `kind-karmada-mgmt` | 16443 |
| `dc-primary` | `kind-dc-primary` | 16444 |
| `dc-secondary` | `kind-dc-secondary` | 16445 |
| `cloud-azure` | `kind-cloud-azure` | 16446 |

Additional: Karmada API host port 16447 → node port 32443. Prometheus receiver 31090; Loki receiver 31091. `cloud-azure` is NOT a real Azure cluster.

## Open technical questions to resolve by tests, not assumption

- Karmada `karmadactl init` certificates / APIService registration using the pinned upstream release and 4 custom kind cluster names.
- Stable Docker network access from each member cluster to management NodePorts; prefer the resolvable management node hostname when possible, otherwise explicitly refresh endpoint IPs on redeploy.
- Karmada cluster allocatable/resource summary and exact available replica calculations; CPU reservations must not starve monitoring or metrics-server.
- Default local StorageClass and Helm chart versions/schema/labels. `helm template` first, then deploy.
- Cross-cluster aggregation in metrics adapter under chosen Docker network/CIDRs; test `metrics.k8s.io` through the Karmada API, not only via members.
- Whether WSL mirrored mode is needed for user's specific FreeLens integration; do not make it mandatory without testing. The host port/API access is the first priority.
