# Validation results

## Latest verified state — 2026-11-08

On the user’s WSL2/Docker Desktop host, all four kind clusters were deleted and recreated. The first `make up` failed on a GitHub CRD download timeout; after a verified cached-asset fallback was implemented, the retry and a further `make up` passed. `make verify`, the complete manual and automatic demos, the three Grafana dashboards, and all five FreeLens connections were checked successfully. The latest detailed evidence is under [Rebuild checkpoint](#rebuild-checkpoint--2026-11-08).

An entirely empty artifact-cache install and the original FreeLens 503 root cause remain unverified. Windows-host telemetry is deferred at the user’s request. A successful tested run does not guarantee repeatability under different network or resource conditions.

The chronological checkpoints below record the actual state *at that time*: early BLOCKED, NOT RUN and incomplete statements are historical and superseded by later results. The [acceptance checklist](ACCEPTANCE_TESTS.md) defines criteria; a command is evidence only when actually executed.

## Historical starter-kit checkpoint — 2026-11-08

Local check on 2026-11-08: `bash -n scripts/*.sh install-karmada-wsl-tools.sh` passed; YAML parsing confirmed the requested image digest on every node in all four kind configurations. `make preflight` passed the naming and pinned CLI checks, then failed because Docker socket access was denied. `make -n bootstrap` shows metrics installation followed by an explicit failure for the still-unimplemented Alloy and observability stack. No Kubernetes runtime checks were executed.

| Check | Status | Evidence |
|---|---|---|
| File syntax / JSON / YAML parsing | Pending local build verification | |
| Metrics-server and Karmada adapter runtime | BLOCKED — no Windows Docker access in this package generation | |
| Four cluster bootstrap | BLOCKED — no Windows Docker access | |
| Observability and two real demos | BLOCKED — no Windows Docker access | |

## Historical preflight checkpoint — 2026-11-08

| Command | Result | Evidence |
|---|---|---|
| `bash -n scripts/*.sh install-karmada-wsl-tools.sh` | PASS | Exit 0 |
| `python3 -m compileall -q app exporter scripts` | PASS | Exit 0 |
| `make verify-names` | PASS | Canonical names reported after excluding internal/generated directories |
| `make preflight` | PASS outside sandbox; BLOCKED inside | Pinned CLI checks pass; Docker socket is inaccessible inside the sandbox but reachable outside it |

Outside the sandbox, `docker info --format '{{.ServerVersion}}'` reported `29.9.2`; `kind get clusters` initially reported no kind clusters. `make bootstrap` passed preflight, then failed on non-executable starter scripts. After correcting the executable bits, the retry created four kind clusters and started Karmada installation. Acceptance checks remain pending.

At this checkpoint, `kubectl --kubeconfig .runtime/karmada/karmada-freelens.yaml --request-timeout=10s get --raw /readyz` returned `ok` with TLS verification enabled, but Karmada initialization was incomplete. The later runtime checkpoint below supersedes this state.

## Runtime checkpoint — 2026-11-08

- User confirmed importing the Karmada API into FreeLens. Following reinitialization with the preserved CA, the backed-up original Karmada credentials returned `ok` from `/readyz` and successfully listed the three clusters from WSL. The Windows connection was not retested after reinitialization.
- `make karmada-up`: PASS after recovery; repeated execution passed, reporting `cloud-azure`, `dc-primary`, and `dc-secondary` as Push and Ready on Kubernetes v1.35.8. This establishes A01 for the observed run, not fresh-install reproducibility.
- `make metrics-up`: initial failure due to missing Go, followed by a missing adapter certificate; after fixes, PASS. Adapter/APIService and member metrics were checked.
- Repeated `make metrics-up`: PASS; the valid adapter serving certificate was reused and both aggregated metrics checks passed again.
- `make verify-fhpa`: PASS. Rollouts and API discovery succeeded; aggregated `/apis/metrics.k8s.io/v1beta1/nodes` and `/pods` each contained data from all three named member clusters. FederatedHPA API exists; a real scaling cycle has not been tested.
- `make bootstrap` on the existing lab: preflight, all four node readiness checks, Karmada and aggregated metrics checks passed; command exited nonzero at its deliberate `Bootstrap incomplete: Alloy and the observability stack are not yet implemented` guard. A fresh installation after these fixes, observability, demos and full A16 remain unverified or incomplete.

## Storage and backend checkpoint — 2026-11-08

- `kubectl --context kind-karmada-mgmt get storageclass`: default `standard`, `rancher.io/local-path`, `WaitForFirstConsumer`; local-path-provisioner deployment Ready. A temporary consuming pod and 1Mi PVC produced `Bound`; the dedicated test namespace was removed.
- `make observability-backends`: PASS for deployment/readiness. PVCs `prometheus-server` 5Gi, `storage-loki-0` 3Gi and `grafana` 1Gi all Bound; Prometheus 2/2, Loki 1/1 and Grafana 1/1 Ready. Services expose NodePorts 31090 and 31091. Retention and ingress data flow still require runtime verification.
- `make observability-collectors`: PASS on all four clusters; rerun also completed successfully. `make verify-observability` passed all rollouts and PVC checks, with all four `prometheus.scrape.kube_state_metrics` targets reporting `up=1`.
- Three short-lived test pods, one per member, each fetched `/-/ready` on management NodePort 31090 and `/ready` on 31091 via the management Docker node IP. Each printed `Prometheus Server is Ready.` and `ready`; the pods were removed.
- Loki `query_range` returned events labelled for all four clusters. A real `Warning` from a deliberately unschedulable temporary pod was returned by Loki; the pod was removed. A scenario marker was returned both directly and through Grafana's Loki datasource proxy.
- Grafana API listed all three dashboards; datasource health for `loki` and `prometheus` returned `OK`. The user confirmed seeing annotations and provided an image showing a Kubernetes `Warning` event rendered on a dashboard. The screenshot does not independently establish scenario-marker rendering or visual rendering on each other dashboard.
- Effective Prometheus arguments included `--storage.tsdb.retention.time=1d`; Loki `/config` showed `retention_period: 1d`, `retention_enabled: true` and `delete_request_store: filesystem`.
- Karmada scheduler and controller-manager Alloy-discovered targets each reported `up=1` in Prometheus.
- Repeated `make bootstrap` after wiring backends and collectors: an initial attempt failed on GitHub release HTTP 504. After switching to the pinned official metrics-server source overlay, all prerequisite and observability readiness checks passed; the command then exited nonzero at the intentional placement-exporter/demo incomplete guard. This was a reconciliation of the existing lab, not a fresh installation.

## 22-pod idle capacity test — 2026-11-08

`free -h` before the test reported 19Gi total and 13Gi available; `nproc` reported 12. The demo manifest requests 250m CPU and 128Mi memory per pod. After `make build load`, temporary deployments used that same image, resources and probes; their `kubectl rollout status` and deployment output showed Ready counts 4/4, 6/6 and 12/12 across the three named members. While all 22 were Ready, `free -h` again reported approximately 13Gi available; `kubectl top pods` reported 11Mi per demo container. The temporary test namespaces were deleted. The test did not apply Karmada propagation or exercise the sequential scenario, load generators, HPA, or sustained high memory/CPU use.

## Placement exporter checkpoint — 2026-11-08

- `make placement-exporter`: PASS after adding a writable temporary volume. Repeated installation completed, with no deployment change on a subsequent identical build. Dedicated ServiceAccount authorization allowed `get deployments` and denied `update deployments` in `demo`.
- With no demo deployment, direct `/metrics` reported `karmada_lab_exporter_poll_success 1` and `karmada_lab_workload_present 0`, without a desired-replica series.
- An ephemeral real Karmada deployment/policy at eight replicas produced ResourceBinding assignments `dc-primary=4`, `dc-secondary=4`, `cloud-azure=0`. Prometheus returned the same assignment values and desired replicas `8`. A separate test returned Ready values `4` and `4` via kube-state-metrics, matching the member Deployment status. Test resources were removed.
- `make verify-observability`: PASS including fresh exporter polling. The complete 4→8→10→16→22→8→4 scenario and CPU-driven FederatedHPA behavior remain NOT RUN.
- Repeated `make bootstrap` on the existing lab passed exporter and observability checks, then exited nonzero at the deliberate `end-to-end demo integration is not yet implemented` guard. Fresh installation remains unverified.

## Manual burst checkpoint — 2026-11-08

`make calibrate` created request-only reservations and confirmed Karmada CPU allocated summaries at 10850m (`dc-primary`), 10350m (`dc-secondary`), and 8850m (`cloud-azure`). The first manual run failed its 10-replica acceptance check: assignments were 2+6+2. Scheduler logs identified the default coarse resource-model estimate as the limiting factor. After changing the pinned scheduler to exact resource-summary estimation and resetting the workload to zero, `STAGE_SECONDS=20 make demo-manual` exited 0. Each row below was confirmed in both the ResourceBinding and the member Deployment available counts.

| Desired | dc-primary Ready/assigned | dc-secondary Ready/assigned | cloud-azure Ready/assigned |
|---:|---:|---:|---:|
| 4 | 2 | 2 | 0 |
| 8 | 3 | 5 | 0 |
| 10 | 4 | 6 | 0 |
| 16 | 4 | 6 | 6 |
| 22 | 4 | 6 | 12 |
| 8 | 3 | 5 | 0 |
| 4 | 2 | 2 | 0 |

Full per-stage timestamps and state are in the ignored local file `.runtime/manual/20261108T095105Z.jsonl`. At 22 replicas, Prometheus reported the same 4+6+12 assignment and `free -h` reported about 12Gi available. Loki returned the stage markers; no FederatedHPA or local load-generator deployments were present after the run. A11/A12 passed for this observed manual run; repeatability on a fresh installation and the automated scenario remain unverified. Scale-in moved replicas out of cloud in this run, which is not a universal rebalance guarantee.

After the run, `make reset-demo` passed at 4 Ready (2+2 on-prem) and emitted a marker. `make calibrate` exited with the expected active-demo protection message and did not reconfigure reservations. The later shared-WSL memory precheck has only been syntax checked so far.

## FederatedHPA checkpoint — 2026-11-08

`make demo-auto` completed with exit 0 using per-cluster generators, two workers initially and a maximum of four, with a 250m CPU limit per generator. FHPA CPU target was 50%, bounds 4–22. At 10:01:11 UTC the observed HPA utilization was 282% of requested CPU, the desired count was 12, and the actual binding and Ready counts were `dc-primary=4`, `dc-secondary=6`, `cloud-azure=2`. The aggregated pod metrics then included all three members. No manual replica writer ran during autoscaling.

After load stopped, delayed metric samples triggered further scaling to 20 before utilization dropped. The HPA then scaled to 8 and subsequently 4 Ready at 10:03:43 UTC, about 128 seconds after the 10:01:35 cooldown observation. Reset removed the FHPA and all three generators remained at zero. The sampled maximum WSL CPU was 59%, and minimum `MemAvailable` was 12961Mi; Windows host telemetry and unsampled peaks were not measured. Detailed snapshots: `.runtime/auto/20261108T100020Z.jsonl`. A13/A14 passed for this run, not a guarantee of repeatability or a particular scale-in duration.

## Operational command checkpoint — 2026-11-08

- `make verify`: PASS on the running lab. Generated fresh Events from all four clusters and a Loki marker; verified ingestion, Grafana datasource health and enabled dashboard annotation definitions, workload consistency and metrics APIs.
- `make up`: PASS twice on the existing lab, including the same health checks. This is not evidence of installation from a fresh WSL environment.
- `make down`: ownership-match and mismatch behavior tested with mocked `kind` and `docker` commands only. No live lab clusters or PVCs were deleted. Live teardown/recreation, Windows-host metrics, and visual confirmation of scenario markers on each dashboard remain NOT RUN.
- Static shell syntax, Python compilation, dashboard JSON, `make verify-names` and `git diff --check`: PASS locally. Hosted CI has not run.
- Actual usage monitoring: Alloy cAdvisor scrape targets `up=1` on all four clusters via the Kubernetes API proxy. Prometheus returned `container_cpu_usage_seconds_total` and `container_memory_working_set_bytes` from all four sources; the demo's actual CPU and memory panel queries returned values for the two members running replicas. These are container metrics, not Windows host metrics.
- The initial expanded Grafana panel check failed because a changed ConfigMap had not reached the loaded dashboard. Adding a dashboard-content hash to the Grafana pod template triggered a refresh; subsequent `make verify` passed, including the new panel definitions and actual usage series.
- Final `make up`: PASS on the existing lab with cAdvisor and refreshed dashboard checks. `python3 -m unittest discover -s tests`: PASS (2 mocked teardown safety cases). Live `make down` and recreation remain NOT RUN.

See `WORK_STATUS.md` for the ongoing work log. None of A01–A16 is claimed as passed by these static checks.

## Grafana accuracy checkpoint — 2026-11-08

`make observability-backends` and `make verify` passed after the dashboard corrections. A real Chromium review of all three provisioned dashboards showed propagation latency data; a focused recheck of the reported historical interval showed individual Ready values of `cloud-azure=10`, `dc-primary=4`, `dc-secondary=6` at their matching vertical positions. The final provisioned replica panels are checked as non-stacked step charts by `verify-telemetry.py`.

Historical Prometheus range queries returned the corrected scheduling and propagation metrics and both FHPA CPU series (50% target, observed peak 282%). The Loki annotation selector returned manual/auto scenario markers and excluded verification-only markers. The scheduler's pending-bindings gauge is not served by Karmada v1.19.1's metrics registry; enqueue rate is shown as a different, explicitly labeled metric, not as queue depth. Resource creation error series can legitimately be absent before the first error; absence alone does not prove health. No new scenario run or fresh installation was performed for this checkpoint.

## HPA inactive-state checkpoint — 2026-11-08

`make placement-exporter` and `make verify` passed. Direct inspection of the deployed exporter with no FHPA returned `karmada_lab_hpa_active 0` and NaN for CPU utilization, CPU target and HPA replica status. A temporary FHPA with target 50% returned active=1, target=50% and observed CPU=0%; the FHPA was then deleted and `make reset-demo` verified four Ready replicas (2+2 on-prem) and stopped load. This tests active/inactive reporting, not another autoscaling or fresh-install run. The user deferred Windows-host telemetry.

## Rebuild checkpoint — 2026-11-08

Pre-teardown `make preflight` and `make verify` passed. `make down` successfully deleted the four ownership-verified lab clusters and their node-local PVC data. On fresh recreation the first `make up` failed while downloading the pinned Karmada CRDs due to a GitHub timeout; after adding a SHA-256-verified cached asset/source fallback, a retry on those freshly created clusters passed `make up` and `make verify`, including Ready members, aggregated metrics, three Bound PVCs and fresh telemetry.

On the recreated clusters, `make demo-manual` passed 4→8→10→16→22→8→4 with all assigned replicas Ready; at 22 the distribution was 4+6+12. `make demo-auto` passed: FHPA observed 265% CPU, increased desired replicas to 12 with Ready distribution 4+6+2, and after stopping load the delayed samples increased the desired count to 20 before scale-in returned to four. Snapshots are `.runtime/manual/20261108T114344Z.jsonl` and `.runtime/auto/20261108T114633Z.jsonl`. First-attempt fresh bootstrap was not successful, and fresh installation with an empty artifact cache has not been tested.

FreeLens initially returned its internal 503 after recreation, even though all four kubeconfigs worked from Windows `kubectl.exe` and Windows could reach the API ports. Deleting the catalog entries removed their contexts from the synchronized files; `make kind-up` regenerated them, but the user still reports connection failure. Investigation remains open.

A subsequent `make up` on the recreated lab also passed current health checks. The installed FreeLens 2.0 application generates its reported 503 internally when its cluster state is disconnected; the underlying cause of that state is still unverified.

The user confirmed a newly imported FreeLens management-cluster entry works with the same effective kubeconfig; FreeLens saved the import as its own copy. The three other newly imported entries remain pending user confirmation, and the precise cause of the original stale catalog entries remains unverified. A Chromium review after rebuilding loaded all three Grafana dashboards and showed new scenario data and annotation lines.

FreeLens follow-up: the user confirmed `dc-primary`, `dc-secondary`, and `cloud-azure` all connect after importing them as new FreeLens-managed entries, in addition to the previously confirmed `karmada-mgmt` and Karmada API. These imports are copies and require refresh after a future rebuild. The original 503 cause remains unverified.
