# Karmada Hybrid Cloud Bursting Lab — v4 agent handoff kit

**Scope:** Four fixed-name kind clusters on Windows+WSL2+Docker Desktop; centralized Karmada; two mutually exclusive burst scenarios and in-cluster observability. Both scenarios have been exercised on the current host; reproducibility from a fresh installation remains unverified.

## Cluster naming — enforced

| kind cluster | purpose | kubectl context | Karmada Cluster object |
| --- | --- | --- | --- |
| `karmada-mgmt` | control plane, Prometheus, Loki, Grafana, monitoring PVCs | `kind-karmada-mgmt` | not joined |
| `dc-primary` | on-prem DC #1 | `kind-dc-primary` | `dc-primary` |
| `dc-secondary` | on-prem DC #2 | `kind-dc-secondary` | `dc-secondary` |
| `cloud-azure` | simulated overflow | `kind-cloud-azure` | `cloud-azure` |

The three members must be Push-registered. Each mgmt and member API gets a fixed Windows localhost port. The mgmt kind node maps NodePorts **32443 -> 16447** (Karmada API), **31090 -> 31090** (Prometheus remote-write) and **31091 -> 31091** (Loki), loopback only. The backend installer creates the matching NodePort Services. Member Pods send to the management Docker node's routed IP, not 127.0.0.1. Those Docker IPs can change after cluster recreation; rerun the collector installer after recreation.

## WSL2 prerequisites

`docker` using Docker Desktop WSL integration, `kind` v0.33.0, `kubectl` v1.35.9, `helm` v3.22.1, `karmadactl` v1.19.1, Python 3 and GNU make. `install-karmada-wsl-tools.sh` installs host tools; `make preflight` checks them and Docker without requiring existing clusters. Store the repository under `/home/<user>/...`, not `/mnt/c`. A sensible WSL limit is 20 GB RAM. All four kind configurations pin `kindest/node:v1.35.8` to digest `sha256:07b2536e30b803ed61d1677a79df6115f798ce64c80f9e22f6ed45afd09323c0`; existing clusters must be recreated separately for an image change to take effect.

## Bootstrap commands

```bash
make up                        # reconcile the lab and run current health checks
make verify                    # recheck clusters, metrics, telemetry and demo readiness
make demo-manual               # 4 -> 8 -> 10 -> 16 -> 22 -> 8 -> 4
make demo-auto                 # CPU-driven burst, scale-in and reset
make reset-demo                # stop HPA/load and restore four Ready replicas
make down                      # delete recorded lab clusters and their local PVC data
```

`make bootstrap` is the underlying entry point for `make up`; `make preflight`,
`make calibrate`, `make build load deploy`, and `make verify-fhpa` remain available
for targeted troubleshooting. `make up` refuses to overwrite an active HPA,
load generator or non-baseline demo; run `make reset-demo` first. `make verify`
creates short-lived Normal Kubernetes Events and a Loki marker to prove telemetry.
`make down` only deletes clusters whose control-plane container IDs match the
private records in `.runtime/kind-owned/`; it deletes their node-local PVC data.
After recreation, import the new kubeconfigs into FreeLens. The prior Karmada
credentials are privately archived under `.runtime/archive/`.

**Default bootstrap:** `make bootstrap` includes member `metrics-server`, the `karmada-metrics-adapter` installer using the **v1.19.1-tagged upstream Karmada** helper, central backends, the placement exporter, collectors and demo baseline. `make verify-fhpa` checks the member APIs, adapter and controller rollouts, APIService and FederatedHPA API registration, and requires aggregated node and pod metrics from all three members. Both burst scenarios have been tested once on the current WSL2 environment; a fresh bootstrap remains unverified. See `docs/VALIDATION_RESULTS.md` for evidence and limitations.

See **`AGENTS.md`**, **`docs/AGENT_START_PROMPT.md`**, **`docs/IMPLEMENTATION_PLAN.md`**, and **`docs/ACCEPTANCE_TESTS.md`** for the complete handoff and priorities.

## Scenario A — manual burst

```bash
make demo-manual
make reset-demo
```

The desired sequence is 4 -> 8 -> 10 -> 16 -> 22 -> 8 -> 4. `make demo-manual` removes FederatedHPA, stops any local load generators, waits for each binding and member Ready count to converge, and records snapshots in `.runtime/manual/`. The default dwell time is 20 seconds; adjust it with `STAGE_SECONDS=60 make demo-manual`. On the current host the full sequence passed with cloud overflow at 16 and 22; see `docs/VALIDATION_RESULTS.md`. Results depend on current capacity and are not a guarantee of future automatic move-back. A Karmada assignment is distinct from a member pod being Ready.

## Scenario B — FederatedHPA automatic burst

- Source `karmada/federated-hpa.yaml`: `autoscaling.karmada.io/v1alpha1`, CPU utilization target 50%, minimum 4, maximum 22.
- CPU metrics: **member** `metrics-server` -> `karmada-metrics-adapter` -> Karmada aggregated `metrics.k8s.io` -> FederatedHPA -> scheduler -> ResourceBinding changes -> member kube-controller-manager.
- A Python HTTP demo server has CPU-bound `/burn?ms=120`; each member's bounded local load generator calls only its local `placement-demo` ClusterIP Service. No ingress, mesh or MultiClusterService is required.
- Generators start with two workers, increase to at most four if needed, and each have a 250m CPU limit. The runner checks WSL CPU/memory, limits each phase to 600 seconds by default and resets on failure. Windows host CPU is not measured. The actual application load and HPA behavior depend on available capacity.

```bash
make demo-auto
# In another terminal if desired:
kubectl --kubeconfig .runtime/karmada/karmada-apiserver.config -n demo get fhpa -w
```

The command waits for CPU-driven cloud overflow, stops load, observes scale-in, then removes the FHPA and restores four Ready replicas. It records timestamped snapshots under `.runtime/auto/`. `make auto-stop` performs the same baseline reset if needed. In the tested run, the HPA briefly continued scaling up after load stopped because prior CPU samples were still arriving; it then scaled down to four. This timing is not guaranteed. The load generators are local Deployments and are **not** propagated by Karmada. A separate service policy provides a local Service in all three members; the cloud Service has no endpoints until cloud replicas exist.

## Observability

All backends live inside `karmada-mgmt`: Prometheus (PVC 5GiB, retention 24h), Loki (PVC 3GiB, retention 24h), Grafana (PVC 1GiB). `make observability-backends` installs the central services and provisions Grafana dashboards and datasources; `make placement-exporter` installs the Karmada placement exporter; `make observability-collectors` installs Alloy and kube-state-metrics in all four clusters. `make verify-observability` checks component readiness, PVCs, metrics from each cluster and a fresh exporter poll. Actual central metrics, Kubernetes Event, marker and placement exporter checks have passed; the user also confirmed a Warning annotation visible on a dashboard. See `docs/VALIDATION_RESULTS.md` for limits. Full visual annotation coverage and complete demo data remain outstanding, so some dashboard panels are empty when the demo is absent.

The observed kind default `standard` local-path StorageClass dynamically binds PVCs. kind node-local PV data do not survive deletion/recreation of the kind container unless host-mounted and backed up. Access Grafana in FreeLens using a port-forward to the `monitoring/grafana` Service; retrieve the generated admin password locally with `kubectl --context kind-karmada-mgmt -n monitoring get secret grafana -o jsonpath='{.data.admin-password}' | base64 -d`.

## Validation & known missing implementation

Syntax-level tests: `bash -n`, Python compile, YAML parse, dashboard JSON validation, naming check.
Runtime checks passed for the existing four-cluster WSL2 lab, Karmada joins, aggregated resource metrics, backend PVC binding, cross-cluster telemetry, manual burst and CPU-driven autoscaling. Still pending: fresh-install reproducibility, actual teardown/recreation, Windows-host resource telemetry and visual verification of scenario annotations on every dashboard.

Official docs:
- https://karmada.io/docs/tutorials/autoscaling-with-resource-metrics/
- https://karmada.io/docs/userguide/autoscaling/federatedhpa/
- https://karmada.io/docs/reference/karmada-api/autoscaling-resources/federated-hpa-v1alpha1/
- https://karmada.io/docs/installation/
- https://kind.sigs.k8s.io/docs/user/configuration/
- https://grafana.com/docs/alloy/latest/collect/logs-in-kubernetes/

## Predefined receiver NodePorts and scenario markers

The backend installer applies `observability/network/nodeports.yaml`. A client inside a member cluster reaches the mgmt **Docker node IP** on 31090/31091; only a Windows/WSL user can use localhost mappings. `scripts/emit-marker.py` posts structured scenario events to Loki NodePort 31091 for Grafana annotations.

### Capacity calibration notes

Run `make calibrate` after all core components in the member clusters are up but **before** deploying the demo. It checks all members first, rejects an active demo, HPA or load generator, validates memory and pod-slot headroom, then installs one low-runtime-CPU `capacity-reservation` Pod per member. It also checks shared WSL `MemAvailable`; override a low-memory warning only after review with `LAB_ALLOW_LOW_MEMORY=1`. The requested CPU leaves nominal 4/6/12 demo slots plus 150m buffer. The script waits for Karmada resource summaries to converge. The scheduler uses exact Cluster resource summaries instead of the default coarse resource-model buckets for this lab. All members share one physical host; these reservations are scheduling requests, not dedicated physical CPU hardware. To recalibrate, remove the demo and HPA, stop load generators, and rerun `make calibrate`.

Service distribution is intentionally governed by `karmada/service-propagation.yaml` and NOT the burst policy, so `cloud-azure` has a ClusterIP Service before its first workload replica arrives. The main overflow `PropagationPolicy` selects only the Deployment.
