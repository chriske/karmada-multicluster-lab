# Karmada hybrid-cloud bursting lab — mandatory agent instructions

You are implementing and validating a reproducible **local laboratory**, not a production Karmada deployment. Read `docs/IMPLEMENTATION_PLAN.md`, `docs/ACCEPTANCE_TESTS.md`, and `docs/ARCHITECTURE_DECISIONS.md` **before editing**. Treat the current repository as **an unverified starter kit**, not a working installation.

## Immutable decisions

1. Host: Ryzen 7700X, 32 GiB RAM, Windows + Ubuntu WSL2 + Docker Desktop (WSL integration), VS Code; Windows FreeLens is the Kubernetes IDE. Target WSL memory limit ~20 GiB.
2. Four **kind cluster names**, used verbatim everywhere: `karmada-mgmt` (Karmada + central observability), `dc-primary`, `dc-secondary`, `cloud-azure` (simulated cloud). Never use generic ordinal member identifiers, generic host names, or location-based sample cluster aliases, including in committed generated configs and docs. `kind-<cluster>` is allowed only where kind generates kubeconfig contexts; Karmada Cluster API names have NO `kind-` prefix.
3. Karmada target `v1.19.1`. Member registration: Push. 3 members form one preference group for on-prem and an overflow cloud group: `dc-primary` and `dc-secondary` first, `cloud-azure` on overflow.
4. Central Prometheus, Loki, Grafana **in Kubernetes `karmada-mgmt`**, not Docker Compose. PVCs: initial 5 GiB, 3 GiB, 1 GiB, respectively. Prometheus and Loki retention **24h**. Single-instance, small-footprint. Confirm kind StorageClass/PVC binding; do not imply data survives kind cluster deletion.
5. Grafana Alloy is the collector, in all four clusters; Kubernetes Events shipped to Loki; warning events and scenario markers shown as Grafana annotations by default. kube-state-metrics runs separately as appropriate. Host monitoring should distinguish container/WSL host and Windows host.
6. No ingress controller or service mesh. Stable, preconfigured NodePorts/`extraPortMappings` for receiving member data: Prometheus 31090, Loki 31091; Karmada API 32443/node → Windows port 16447. Kubernetes API host ports 16443–16446. From member-cluster pods, do NOT use `127.0.0.1` to reach management; test Docker network reachability. Grafana UI from Windows via FreeLens port-forward.
7. Two independent demos: A) manual replica count 4→8→10→16→22→8→4; B) FederatedHPA CPU-target 50%, bounds 4–22, per-cluster local HTTP load generators; explicitly reset state between scenarios.
8. **FederatedHPA dependencies must install by default as part of the bootstrap**, not as a manual afterthought: member `metrics-server` on all 3, Karmada `karmada-metrics-adapter` with APIService, RBAC and certificates, and success checks. Do not mark bootstrap successful unless the metrics APIs are usable. `make bootstrap` already includes preliminary automation; agent must validate and harden it.
9. Version-pin CLI binaries, images, Helm charts and dependencies; do not silently use `latest`. Keep installers idempotent, errors actionable, secrets out of Git. Workload CPU/memory scheduling and metrics must distinguish *requested capacity*, *actual use*, *assigned replicas*, and *Ready replicas*.
10. No claims of operational success without executing and reporting checks on the user's target environment. If you lack Docker/WSL access, run syntax/template tests and explicitly mark end-to-end tests blocked.

## Working behavior

- Inspect current files before modifying and preserve useful functionality. Follow the ordered stages and acceptance tests in `docs/`.
- Prefer small commits/checkpoints per stage, with reason, command executed, result, and next action.
- Never introduce another name for a cluster. `make verify-names` should be mandatory in CI/preflight.
- Always verify APIs and readiness, not just whether `kubectl apply` returned success.
- On failure, fix root cause and retry narrowly; do not suppress errors with `|| true` for required steps.
- Do not loosen kubelet TLS outside the local kind-only resource metrics scope or publish management APIs on `0.0.0.0` without justification.
- No new heavyweight operators, meshes, ingress, extra Prometheus deployments or other external systems without approval.
- Never run machine-wide Docker cleanup commands (`docker system prune`, volume prune, indiscriminate container deletion) or delete any clusters/volumes not created by this lab. The user may have unrelated Docker workloads.
- The operational interface should become `make up`, `make verify`, `make demo-manual`, `make demo-auto`, `make reset-demo`, `make down`; Makefile target names may be aliases of existing targets.

## Official reference URLs

- https://karmada.io/docs/tutorials/autoscaling-with-resource-metrics/
- https://karmada.io/docs/userguide/autoscaling/federatedhpa/
- https://karmada.io/docs/installation/
- https://raw.githubusercontent.com/karmada-io/karmada/v1.19.1/hack/deploy-metrics-adapter.sh
- https://kind.sigs.k8s.io/docs/user/configuration/
- https://grafana.com/docs/alloy/latest/
