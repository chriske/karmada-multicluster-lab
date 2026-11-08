# In-cluster observability – design and handoff

A full explanation of data paths, dashboard panels and real Grafana screenshots is in [the architecture guide](../docs/ARCHITECTURE.md).

- `karmada-mgmt` / `monitoring`: one Prometheus (24h, PVC 5Gi), one Loki (24h, PVC 3Gi, compactor), Grafana (PVC 1Gi), Alloy, kube-state-metrics, Karmada state exporter.
- `dc-primary`, `dc-secondary`, `cloud-azure`: Alloy and kube-state-metrics collectors, no metrics/log backend.
- `observability/helm-values/*.yaml` and the installers pin chart versions and provision Grafana datasources and dashboards. See `docs/VERSIONS.md`.
- Cross-cluster connectivity requires an explicit reachable endpoint for Loki push and Prometheus remote-write, rather than bare `monitoring.svc` DNS from member clusters.
- Included dashboard annotations expect a Loki datasource with UID `loki` and a log stream label `source_type=k8s-event` plus `source_cluster` equal to one of the four canonical names.
- Alloy collects Kubernetes Events in JSON and adds cluster/source labels in `loki.write`. It also collects kube-state-metrics and cAdvisor metrics in all clusters; management Alloy scrapes Karmada controllers and the placement exporter.
- Prometheus samples are retained for 24h; Loki retention compaction/deletion is asynchronous. PVC space must still be monitored.
- The current kind `standard` StorageClass dynamically bound the three PVCs in the observed rebuild. Verify with `kubectl --context kind-karmada-mgmt -n monitoring get pvc`; cluster deletion removes node-local data.
- The PVCs survive ordinary Pod recreation while the kind node and its storage remain; deletion/recreation of the kind cluster destroys node-local data. Pod-recreation persistence has not been separately established as a dedicated acceptance test.
