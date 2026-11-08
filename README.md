# Karmada Hybrid Cloud Bursting Lab — v4 agent handoff kit

**Scope:** Four fixed-name kind clusters on Windows+WSL2+Docker Desktop; centralized Karmada; two mutually exclusive burst scenarios; initial Grafana JSON and observability Helm values carried forward from v2. This is a static/tested-for-syntax **implementation kit, not yet a proven end-to-end deployment**.

## Cluster naming — enforced

| kind cluster | purpose | kubectl context | Karmada Cluster object |
| --- | --- | --- | --- |
| `karmada-mgmt` | control plane, Prometheus, Loki, Grafana, monitoring PVCs | `kind-karmada-mgmt` | not joined |
| `dc-primary` | on-prem DC #1 | `kind-dc-primary` | `dc-primary` |
| `dc-secondary` | on-prem DC #2 | `kind-dc-secondary` | `dc-secondary` |
| `cloud-azure` | simulated overflow | `kind-cloud-azure` | `cloud-azure` |

The three members must be Push-registered. Each mgmt and member API gets a fixed Windows localhost port. The mgmt kind node maps NodePorts **32443 -> 16447** (Karmada API), **31090 -> 31090** (Prometheus remote-write) and **31091 -> 31091** (Loki), loopback only. A Kubernetes NodePort Service with matching `nodePort` needs to be created for Prometheus and Loki via Helm/manifest (still outstanding). Member Pods must send to the management Docker node's routed IP, not 127.0.0.1. Those Docker IPs can change after cluster recreation.

## WSL2 prerequisites

`docker` using Docker Desktop WSL integration, `kind` v0.33.0, `kubectl` v1.35.9, `helm` v3.22.1, `karmadactl` v1.19.1, Python 3 and GNU make. `install-karmada-wsl-tools.sh` installs host tools; `make preflight` checks them and Docker without requiring existing clusters. Store the repository under `/home/<user>/...`, not `/mnt/c`. A sensible WSL limit is 20 GB RAM. All four kind configurations pin `kindest/node:v1.35.8` to digest `sha256:07b2536e30b803ed61d1677a79df6115f798ce64c80f9e22f6ed45afd09323c0`; existing clusters must be recreated separately for an image change to take effect.

## Bootstrap commands

```bash
make preflight                 # host tools and Docker; no clusters required
make bootstrap                 # kind + Karmada + metrics; reports incomplete observability
make calibrate                 # CPU request-only reservations targeting 4/6/12 slots
make build load                # Docker build, kind load into three members
make deploy                    # namespace + deployment + local Service + two policies
make verify-fhpa               # member metrics-server + Karmada aggregated APIService
```

**Default bootstrap change (v4):** `make bootstrap` now includes member `metrics-server` and the `karmada-metrics-adapter` installer directly, using the **v1.19.1-tagged upstream Karmada** helper. `make verify-fhpa` checks the 3 metrics-server deployments, their node metrics, the adapter deployment, Karmada APIService and FederatedHPA API registration. No human adapter-install checkpoint is part of the intended flow. **The new script is syntactically checked but has not yet been tested against a running WSL2/Docker/Karmada lab.** The coding agent must test and fix it before declaring bootstrap done.

See **`AGENTS.md`**, **`docs/AGENT_START_PROMPT.md`**, **`docs/IMPLEMENTATION_PLAN.md`**, and **`docs/ACCEPTANCE_TESTS.md`** for the complete handoff and priorities.

## Scenario A — manual burst

```bash
make manual
```

Desired sequence: 4 -> 8 -> 10 -> 16 -> 22 -> 8 -> 4, adjustable with `STAGE_SECONDS=60 make manual`. `make manual` removes FederatedHPA first. **These replica counts do not guarantee exact per-cluster allocations**: the capacity calibration is modeled with CPU-request-only reservation Pods but not yet verified against a live scheduler; test overflow against real Karmada `Cluster.status.resourceSummary` and `ResourceBinding.spec.clusters` values. A Karmada assignment does not guarantee that a pod has been scheduled on the member.

## Scenario B — FederatedHPA automatic burst

- Source `karmada/federated-hpa.yaml`: `autoscaling.karmada.io/v1alpha1`, CPU utilization target 50%, minimum 4, maximum 22.
- CPU metrics: **member** `metrics-server` -> `karmada-metrics-adapter` -> Karmada aggregated `metrics.k8s.io` -> FederatedHPA -> scheduler -> ResourceBinding changes -> member kube-controller-manager.
- A Python HTTP demo server has CPU-bound `/burn?ms=120`; a bounded, always-on load generator runs in each member and calls only **its local** `placement-demo` ClusterIP Service. No ingress, mesh or MultiClusterService required.
- Starting workers=4 per cluster, HPA cannot be guaranteed to use overflow until workload requests, node scheduling capacity and CPU load are empirically tuned. Monitor the physical WSL/Windows CPU as well as request reservations.

```bash
make auto-start
kubectl --kubeconfig .runtime/karmada/karmada-apiserver.config -n demo get fhpa -w
# separate terminal:
kubectl --kubeconfig .runtime/karmada/karmada-apiserver.config -n demo get resourcebinding -w
make auto-stop
```

After `make auto-stop`, default HPA downscale may have already altered replica targets, so reset to 4 before running manual tests. The loadgenerator is a local Deployment and is **not** propagated by the Karmada policy. A **separate** Karmada service PropagationPolicy deploys the local Service in all three member clusters to enable in-cluster traffic, but local Services without endpoints will produce errors until replicas exist, which is expected for the burst cloud cluster.

## Observability design retained from v2

All backends live inside `karmada-mgmt`: Prometheus (PVC 5GiB, retention 24h), Loki (PVC 3GiB, retention 24h), Grafana (PVC 1GiB). Alloy can collect Kubernetes Events via `loki.source.kubernetes_events`, plus kube-state-metrics scraping. Three Grafana dashboard JSON drafts are carried forward, now with basic FederatedHPA overview panels and Loki annotations (Warning events and scenario milestones). **The chart values are starting points and the actual Helm installation, remote-write receiver, NodePort services, Alloy agents, scenario event production, Grafana datasource provisioning, and state-exporter deployment are not yet wired end-to-end.** Do not expect populated dashboard panels from `make kind-up` alone.

Cluster names are consistent in policies, scripts, dashboards. A minimum local-path/default StorageClass must be configured before deploying the monitoring PVCs. kind node-local PV data do not survive deletion/recreation of the kind container unless host-mounted and backed up.

## Validation & known missing implementation

Syntax-level tests: `bash -n`, Python compile, YAML parse, dashboard JSON validation, naming check.
Run-time *pending*: WSL2 Kubernetes four-cluster installation, Karmada init/join + TLS / DNS, metrics adapter, Helm charts + PVC, cross-cluster receiver connectivity, real-cluster validation of CPU-request reservations, Alloy collectors and complete Grafana metrics.

Official docs:
- https://karmada.io/docs/tutorials/autoscaling-with-resource-metrics/
- https://karmada.io/docs/userguide/autoscaling/federatedhpa/
- https://karmada.io/docs/reference/karmada-api/autoscaling-resources/federated-hpa-v1alpha1/
- https://karmada.io/docs/installation/
- https://kind.sigs.k8s.io/docs/user/configuration/
- https://grafana.com/docs/alloy/latest/collect/logs-in-kubernetes/

## Predefined receiver NodePorts and scenario markers

After the respective Helm releases exist, apply `observability/network/nodeports.yaml`; it creates additional NodePort services selected by Helm pod labels (verify actual labels for pinned charts before using). A client inside a member cluster must reach the mgmt **Docker node IP** on 31090/31091; only a Windows/WSL user can use localhost mappings. An optional `scripts/emit-marker.py` posts structured scenario events to Loki NodePort 31091; they appear as Grafana annotations when the Loki backend and datasource are ready.

### Capacity calibration notes

Run `make calibrate` after all core components in the member clusters are up but **before** deploying the demo. This installs one locally created, low-runtime-CPU `capacity-reservation` Pod into each member (separate `karmada-lab-system` namespace). It computes a request value from allocatable minus existing Pod requests, leaving roughly 4/6/12 demo-pod CPU slots plus 150m buffer. Memory, MaxPods, scheduler estimation timing and future loadgen requests may change the effective capacity. This is intentionally a demonstration of Kubernetes **requested** capacity, not independent physical CPU hardware. The member clusters share the same host. To recalibrate, stop the demo and rerun `make calibrate`.

Service distribution is intentionally governed by `karmada/service-propagation.yaml` and NOT the burst policy, so `cloud-azure` has a ClusterIP Service before its first workload replica arrives. The main overflow `PropagationPolicy` selects only the Deployment.
