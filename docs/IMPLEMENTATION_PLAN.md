# Agent implementation plan — Karmada hybrid burst laboratory

## End state / definition of done

With a fresh Ubuntu WSL2 environment (Docker Desktop integration, tools installed), a **single documented entry command** creates or reconciles the four clusters, installs Karmada and its required controllers + **all** CPU-based FederatedHPA dependencies, installs central observability with PVCs/24h retention and per-cluster collection, creates the sample app and policies, and gives operationally useful Grafana dashboards and Windows FreeLens imports. Two demo commands reproducibly show manual and automatic cloud bursting. Real test results are recorded in `docs/VALIDATION_RESULTS.md`.

## Dependency graph

1. Host prerequisite validation (Docker Desktop, WSL, CLI versions, RAM).
2. Four kind clusters with fixed names / API ports / NodePorts, internal routing, FreeLens contexts.
3. Karmada install in mgmt, Push join three members, verify cluster statuses.
4. Metrics-server in each member + Karmada metrics-adapter in mgmt (automatically during bootstrap); verify aggregated metrics path.
5. StorageClass and central monitoring stack (Prometheus/Loki/Grafana PVCs, 24h retention); member Alloy/kube-state-metrics; central Alloy/Karmada scrape.
6. Custom exporter and event/annotation flow; Grafana provisioning.
7. Demo app, service/policies and capacity reservations.
8. Manual scenario + reset; automatic FederatedHPA loadgen scenario + reset.
9. System-level smoke tests, WSL resource telemetry, FreeLens usability, docs.

## Stage P0 — audit & pin [must be first]

- Compare README/Makefile/scripts with official Karmada v1.19.1 docs and pinned helper (NOT trunk/latest). Confirm Kubernetes version and image digest, kind, Helm, Alloy, Grafana, Prometheus, Loki chart versions; publish `docs/VERSIONS.md`.
- Audit all YAML, shell and Python, inspect unused/placeholder paths. No duplicate metrics adapter or namespace. Validate `kubectl` contexts and kubeconfig TLS/SAN issues.
- Confirm WSL2 can run Docker and available memory; warn if too low but allow user to override.
- Verify and document whether default kind StorageClass dynamically binds PVCs; install small local-path provisioner only if genuinely required.
- Read `docs/ACCEPTANCE_TESTS.md` and implement automated checks early.

## Stage P1 — deterministic bootstrap + FederatedHPA dependencies [highest priority]

- Implement `make bootstrap`/`make up` with idempotency and readiness checks. Fixed cluster names and API host ports, adapter API separate port.
- `metrics-server` pinned version on `dc-primary`, `dc-secondary`, `cloud-azure`. Kind-only kubelet serving TLS workaround where required; no silent patch failures. Wait for `kubectl top pods/nodes` to work in each member.
- Auto-install `karmada-metrics-adapter` **from pinned Karmada v1.19.1 official deployment helper and manifests** (`hack/deploy-metrics-adapter.sh`). Its inputs are the management cluster kubeconfig/context and the Karmada virtual API kubeconfig/context. Verify `apiservice/v1beta1.metrics.k8s.io` availability *in the Karmada API* and successful `get --raw /apis/metrics.k8s.io/v1beta1` discovery. Check adapter pod/service/certs/logs on failure.
- Ensure the Karmada FederatedHPA controller is actually running/enabled, API CRD available, and `kubectl get federatedhpa` works. No default-enabled autoscaling on the manual test workload: dependencies preinstalled, FederatedHPA CR created only in auto scenario.
- If time/complexity limited, fully finish this stage and test before adding dashboards. Never report it complete on syntax-only evidence.

## Stage P2 — observability backends and collection

- Choose/pin Helm charts. Install central Prometheus, Loki single-binary, Grafana in `karmada-mgmt`. Configure 5/3/1Gi PVCs and retention 24h for Prometheus & Loki (including Loki compactor). Provision Grafana datasources, dashboards and annotations from Git/ConfigMaps. Use security-conscious local values.
- Install Alloy per cluster with RBAC for Kubernetes Events and metrics discovery/scraping. Either expose central remote-write receiver and Loki push via Service NodePorts + kind cross-cluster Docker reachability, or implement an equally simple documented architecture without ingress.
- Deploy kube-state-metrics (not an Alloy-native kube-state-metrics server) where needed; scrape member workload and Karmada control plane metrics. Preserve common `source_cluster` (telemetry source) and `member_cluster` (Karmada scheduled target) semantics; do not conflate them.
- K8s Events via Alloy's `loki.source.kubernetes_events`, central Loki. Scenario markers and Karmada ResourceBinding transitions as structured events. Warning and scenario annotations enabled *by default* on all 3 dashboards. Test one real Warning and one marker visibly rendering.
- Distinguish logical allocated/requested cluster capacity from host true CPU/memory consumption; no misleading host panels.
- Check retention settings, PVC Bound, restart/rollout health, remote write receive, Loki queries and data freshness.

## Stage P3 — workload and deterministic manual burst

- Build the app image and load it into all 3 kind members. Install local services in each cluster, propagated separately from demo Deployment. Apply `Divided` with on-prem cluster preferences and Azure overflow.
- Capacity calibrator should inspect node allocatable and current requests and reserve safe CPU/memory/pod resources without starving system pods. Exclude demo pods appropriately. Test Karmada `Cluster.status.resourceSummary` and ResourceBinding replicas. Use 4/6/12 nominal target slots as a **calibrated target**, not an unproven guarantee.
- `make demo-manual`: reset HPA/loadgen, scale 4→8→10→16→22→8→4, verify desired/assigned/Ready snapshots, mark phases to Loki, and surface on dashboards. Ensure cloud replicates only after on-prem capacity is exhausted **when scheduling actually permits**; if not, capture why and fix policy/calibration.
- `make reset-demo` returns controlled baseline and avoids race with an active HPA.

## Stage P4 — FederatedHPA automatic burst

- `make demo-auto`: verify metrics dependency availability, restore 4 replicas and no manual scale writer, apply FederatedHPA CPU 50%, min4/max22, local per-cluster loadgen; drive CPU by `/burn?ms=120` and scale load gradually. No ingress, mesh or multi-cluster service needed for the local demo.
- Observe end-to-end chain: CPU use -> per-member metrics-server -> Karmada aggregated API -> FederatedHPA status -> desired Deployment replicas -> Karmada ResourceBinding assigned targets -> actual member Ready replicas -> scale-down. Include timeline annotations.
- Control load safely on shared 7700X/32GiB desktop; bounded concurrency, teardown, protect Windows host. If autoscaling won't burst, investigate metrics aggregation, CPU requests, capacity calibration, readiness and load placement rather than faking success.

## Stage P5 — QA / delivery

- `make verify` runs cluster health, all member metrics API, Karmada metrics API, PVCs, remote-write, Loki, dashboard provisioning, annotation query and workload consistency. `make verify-names` ensures consistent names.
- Demonstrate Windows FreeLens import, four clusters, optional Karmada API context, UI service access by port-forward. Keep kubeconfigs private in `.runtime/`.
- Record actual command output and test results in `docs/VALIDATION_RESULTS.md`, including environment/version, failure cases, remaining limitations. Document local host/WSL stop/start and clean teardown, PVC deletion warnings.
- No status 'complete' without real runtime tests. No requirements handwaving (especially metrics-adapter, event annotations, cross-cluster receivers).

## Agent cadence and guardrails

Implement stage by stage. After each stage provide (a) changed files, (b) test commands + pass/fail evidence, (c) blockers, (d) next stage. Prefer autonomous investigation over questions. Stop to ask the user only when an immutable decision must change or when access/privileges to their WSL/Docker are unavailable. Do not invent successful cluster tests.
