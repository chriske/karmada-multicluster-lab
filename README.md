# Karmada Hybrid Cloud Bursting Lab

**English** | [Magyar](README.hu.md)

This lab uses four separate kind Kubernetes clusters on one Windows + WSL2 + Docker Desktop host to demonstrate how Karmada distributes application replicas between on-premises clusters and a **simulated** cloud cluster. FreeLens is used to inspect the clusters, and Grafana shows their events and metrics.

For a detailed explanation, architecture diagrams, walkthroughs of both scenarios, and Grafana screenshots, see **[How the lab works: architecture and scenarios](docs/ARCHITECTURE.md)**.

## What can you observe?

| Cluster | Role |
| --- | --- |
| `karmada-mgmt` | Karmada control plane and central Prometheus, Loki and Grafana |
| `dc-primary`, `dc-secondary` | Member clusters simulating the preferred on-premises environment |
| `cloud-azure` | Local cloud simulation used for overflow; it is not an Azure service |

A `PropagationPolicy` selects target clusters for the `placement-demo` Deployment created in the Karmada API. The policy prefers the two on-premises clusters; if the estimated capacity there cannot accommodate every replica, `cloud-azure` can receive the remainder. Karmada divides the desired replicas, and each member cluster's Kubernetes controllers create and start the Pods. **Desired**, **assigned**, and actually **Ready** replica counts describe different states.

The lab runs two separate scenarios:

- **Manual burst:** the command sets the desired count to 4→8→10→16→22→8→4. In the latest test, all replicas up to 10 ran on-premises; at 22 the distribution was 4+6+12.
- **Automatic burst:** a `FederatedHPA` adjusts the desired count based on Pod CPU utilization; the system scales back in after the local load generators stop. The 50% target measures utilization **relative to the Pods' CPU requests**.

The 4/6/12 capacity is a scheduling target calculated for this lab: reservation Pods hold CPU requests. All three members share the same physical host; their resources are not physically independent. The exact distribution depends on actual capacity and scheduler state.

## Start and operate the lab

Run these commands from the project root in WSL:

```bash
make up             # create or reconcile the lab, then verify it
make verify         # check the current state and telemetry flows
make demo-manual    # manual 4→8→10→16→22→8→4
make demo-auto      # FederatedHPA load, burst and scale-in
make reset-demo     # stop HPA and load; return to 4 Ready replicas
make down           # delete recorded lab clusters and their local data
```

Run the demos sequentially; their commands establish the required starting state. `make up` refuses to overwrite an active HPA, load generator, or non-baseline replica count; run `make reset-demo` first in that case. `make verify` creates Kubernetes Events and a Loki marker for verification.

**`make down` deletes the lab clusters and their local Prometheus, Loki and Grafana data.** It checks ownership using recorded container IDs; local PVC contents do not survive kind cluster deletion. Rebuilding also affects FreeLens connections.

### Prerequisites

You need Windows, Ubuntu WSL2, Docker Desktop with WSL integration, and `docker`, `kind` v0.33.0, `kubectl` v1.35.9, Helm v3.22.1, `karmadactl` v1.19.1, Python 3, Git, OpenSSL, curl and GNU make. Keep the project in the WSL filesystem, for example under `/home/<user>/karmada-lab`. The target WSL memory limit is about 20 GiB. The [version inventory](docs/VERSIONS.md) records the pins, and `make preflight` checks the tools and Docker. `install-karmada-wsl-tools.sh` installs the pinned host tools.

## FreeLens and Grafana

`make up` writes the four kind kubeconfigs to the private `.runtime/freelens/` directory and the Windows-accessible Karmada API configuration to `.runtime/karmada/karmada-freelens.yaml`. These files contain credentials and must not be committed. In FreeLens, open Grafana with a port-forward to the `monitoring/grafana` Service. Retrieve the admin password locally:

```bash
kubectl --context kind-karmada-mgmt -n monitoring get secret grafana -o jsonpath='{.data.admin-password}' | base64 -d
```

Recreating kind clusters generates new certificates and kubeconfigs. Entries added with FreeLens **Add from kubeconfig** may use their own copies, which must be refreshed or reimported. Removing a synchronized entry can also remove its context from the source file; run `make kind-up` to regenerate the four kind kubeconfigs if that happens. The precise cause of a previously observed FreeLens 503 is unknown; newly imported entries restored all five connections.

## Status and further documentation

On the rebuilt lab, `make up`, `make verify`, and both the manual and automatic demos passed. The first installation attempt during the rebuild stopped when the GitHub CRD download timed out; retrying with a verified cached archive succeeded. **Installation with a completely empty download cache has not been verified.** Separate Windows-host metrics are not currently a priority.

- [Detailed architecture and scenarios](docs/ARCHITECTURE.md) · [Magyar változat](docs/ARCHITECTURE.hu.md)
- [Demo runbook and diagnostic queries](scenarios/01-06-burst-runbook.md)
- [Observability components](observability/README.md)
- [Executed checks and limitations](docs/VALIDATION_RESULTS.md)
- [Ongoing work log](docs/WORK_STATUS.md)
- [Acceptance tests](docs/ACCEPTANCE_TESTS.md), [implementation plan](docs/IMPLEMENTATION_PLAN.md), [architecture decisions](docs/ARCHITECTURE_DECISIONS.md)
- [Karmada FederatedHPA documentation](https://karmada.io/docs/userguide/autoscaling/federatedhpa/), [Karmada resource-metrics autoscaling tutorial](https://karmada.io/docs/tutorials/autoscaling-with-resource-metrics/), [Grafana Alloy](https://grafana.com/docs/alloy/latest/)
