# Guided demo: policy → on-prem → overflow → recovery

For an explanation of the architecture, both scenarios and Grafana panels, see [the architecture guide](../docs/ARCHITECTURE.md). This runbook provides operational checks and PromQL.

## Preconditions

- `dc-primary` and `dc-secondary` represent on-prem and `cloud-azure` represents cloud.
- All three members are Ready; the selected Karmada v1.19.1 startup was adapted to use Push registration for all three.
- The app image has been built and loaded into all three kind clusters.
- The `demo` Namespace exists both in Karmada and in every member cluster.
- Source Deployment and PropagationPolicy have been applied to the **Karmada API**, not to an individual member.
- `karmada_lab_exporter_poll_success == 1`, `cluster_ready_state == 1` for all members, and `kube_deployment_status_replicas_available` is collected from each member with distinct `member_cluster` labels.
- Capacity reservation calibrated to on-prem target free capacity of about 4+6 replicas and cloud capacity of about 12, verified against live Karmada `Cluster.status.resourceSummary`. This is a *test target*, not a built-in kind property or guaranteed scheduler output.

## Open these dashboard tabs

1. `Karmada | Hybrid Cloud Overview` – start here
2. `Karmada | Scheduler & Propagation` – investigate scheduling behavior
3. `Karmada | Cluster Capacity & Placement` – explain resource constraints

## Commands

Read state:

```sh
KARMADA="$PWD/.runtime/karmada/karmada-apiserver.config"
kubectl --kubeconfig "$KARMADA" get clusters
kubectl --kubeconfig "$KARMADA" -n demo get resourcebindings -o json
for m in dc-primary dc-secondary cloud-azure; do
  echo "----- $m -----"
  kubectl --context "kind-$m" -n demo get deployment placement-demo --ignore-not-found -o wide
  kubectl --context "kind-$m" -n demo get pods -l app=placement-demo -o wide
done
```

Run the complete sequence and inspect its timestamped snapshots:

```sh
make demo-manual
```

**Important:** wait for each prior state to converge and inspect both Karmada assignment and Kubernetes readiness. A 'scale' command returning success only means the desired number was patched in the control plane.

## Acceptance checks

- 4, 8, and 10 replicas: on-prem preferred, no cloud assignment *when the advertised primary capacity is sufficient*.
- 16 and 22 replicas: `cloud-azure` receives overflow replicas *once on-prem capacity cannot fit the request*.
- Scale-down: verify whether cloud assignments are reduced first; log any divergence and the binding transitions.
- The validated sequence is limited to the seven stages above. Requests beyond simulated capacity and forced re-evaluation after adding capacity are separate, unvalidated experiments; they are not part of `make demo-manual`. Queue depth is unavailable as described below.

## Suggested Prometheus queries

```promql
sum(karmada_lab_desired_replicas{namespace="demo",workload="placement-demo"})
```

```promql
sum by(member_cluster)(karmada_lab_assigned_replicas{namespace="demo",workload="placement-demo"})
```

```promql
sum by(member_cluster)(kube_deployment_status_replicas_available{namespace="demo",deployment="placement-demo"})
```

```promql
100 * cluster_cpu_allocated_number / cluster_cpu_allocatable_number
```

```promql
sum by (result)(increase(karmada_scheduler_schedule_attempts_total[5m]))
```

```promql
sum by (event) (rate(karmada_scheduler_queue_incoming_bindings_total[5m]))
```

The enqueue rate above is not queue depth. Karmada v1.19.1 registers its pending-bindings gauge in a different registry from the one served by the scheduler metrics endpoint, so its queue depth is unavailable here.

## Expected diagnostics for anomalies

- Binding says 6 on cloud, Deployment desired says 6, only 4 Ready → **member cluster scheduling/startup** issue, inspect Pending pods, Events, image pull and node capacity.
- Binding says 0 on cloud though on-prem has Pending pods → look at Karmada resource summary freshness, estimates, policies and scheduler state. The Karmada estimate may differ from the member Kubernetes scheduler.
- Binding unchanged after new capacity appeared → this may be normal; check trigger/rebalance semantics separately.
- `cluster_cpu_allocated_number` is high but actual CPU usage low → expected for reservation Pods (requests are not actual consumption).
