# Version inventory

This table records the versions currently selected or observed. A pinned version
is not evidence that every component has been validated end to end.

| Component | Version / source |
|---|---|
| kind | v0.33.0 |
| kind node | v1.35.8, sha256:07b2536e30b803ed61d1677a79df6115f798ce64c80f9e22f6ed45afd09323c0 |
| kubectl | v1.35.9 |
| Helm | v3.22.1 |
| Karmada / karmadactl | v1.19.1; control-plane Kubernetes images explicitly pinned to v1.36.2 |
| metrics-server | v0.8.0 |
| Prometheus | chart 29.45.1, app v3.16.0; OCI `ghcr.io/prometheus-community/charts/prometheus` |
| Loki | chart 21.0.0, app 3.7.9; OCI `ghcr.io/grafana-community/helm-charts/loki` |
| Grafana | chart 14.4.0, app 13.3.0; OCI `ghcr.io/grafana-community/helm-charts/grafana` |
| Alloy | chart 1.15.0, app v1.21.3 |
| kube-state-metrics | chart 9.0.0, app 2.20.0 |
| Placement exporter | local image `karmada-lab/placement-exporter:0.1.0`; Python 3.12 Alpine base digest `sha256:e064671ca452259bab50e8e2c7bd896e39e9a343bb06ca25234adf6fe18d0fc7`; exact Python package versions in `exporter/requirements.txt` |

`scripts/install-observability-backends.sh` verifies chart archives by SHA-256
before rendering and installing. The rendered manifests and deployed container
images must be checked during validation; chart app versions alone are not an
image inventory. P0 remains open for the remaining application and dependency audit.
