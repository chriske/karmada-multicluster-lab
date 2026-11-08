# In-cluster observability – design and handoff

- `karmada-mgmt` / `monitoring`: one Prometheus (24h, PVC 5Gi), one Loki (24h, PVC 3Gi, compactor), Grafana (PVC 1Gi), Alloy, kube-state-metrics, Karmada state exporter.
- `dc-primary`, `dc-secondary`, `cloud-azure`: Alloy and kube-state-metrics collectors, no metrics/log backend.
- Start with `observability/helm-values/*.yaml`; chart versions and Grafana provisioning must be pinned/completed before deployment.
- Cross-cluster connectivity requires an explicit reachable endpoint for Loki push and Prometheus remote-write, rather than bare `monitoring.svc` DNS from member clusters.
- Included dashboard annotations expect a Loki datasource with UID `loki` and a log stream label `source_type=k8s-event` plus `source_cluster` equal to one of the four canonical names.
- A dedicated Alloy configuration with `loki.source.kubernetes_events` (`log_format=json`) and `loki.process` static labels must be deployed in all clusters before event annotations will show actual data.
- Prometheus samples are retained for 24h; Loki retention compaction/deletion is asynchronous. PVC space must still be monitored.
- Review PVC provisioning: `kubectl --context kind-karmada-mgmt get storageclass`, inspect default; install a dynamic local-path provisioner if necessary.
- Validate persistence after pod recreation. Deleting the kind node/cluster destroys container-backed data absent host bind mounts or backups.
