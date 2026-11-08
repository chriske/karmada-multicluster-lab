#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
KCFG="${KARMADA_CONFIG:-$PWD/.runtime/karmada/karmada-apiserver.config}"
HOST=kind-karmada-mgmt
IMAGE=karmada-lab/placement-exporter:0.1.0
umask 077
mkdir -p .runtime/exporter
kubectl --kubeconfig "$KCFG" create namespace demo --dry-run=client -o yaml | kubectl --kubeconfig "$KCFG" apply -f -
kubectl --kubeconfig "$KCFG" apply -f exporter/karmada-access.yaml
python3 - "$KCFG" <<'PY'
import base64, json, pathlib, subprocess, sys, time
kubeconfig = sys.argv[1]
for attempt in range(60):
    proc = subprocess.run(['kubectl', '--kubeconfig', kubeconfig, '-n', 'demo', 'get', 'secret',
                           'karmada-lab-exporter-token', '-o', 'json'], check=True, capture_output=True, text=True)
    data = json.loads(proc.stdout).get('data', {})
    if data.get('token'):
        break
    time.sleep(2)
else:
    sys.exit('Karmada did not populate the exporter service-account token within 120 seconds')
token = base64.b64decode(data['token'], validate=True).decode()
ca = base64.b64encode(pathlib.Path('.runtime/karmada/pki/ca.crt').read_bytes()).decode()
config = {'apiVersion': 'v1', 'kind': 'Config',
          'clusters': [{'name': 'karmada-apiserver', 'cluster': {
              'server': 'https://karmada-apiserver.karmada-system.svc:5443', 'certificate-authority-data': ca}}],
          'users': [{'name': 'exporter', 'user': {'token': token}}],
          'contexts': [{'name': 'karmada-apiserver', 'context': {'cluster': 'karmada-apiserver', 'user': 'exporter'}}],
          'current-context': 'karmada-apiserver'}
pathlib.Path('.runtime/exporter/kubeconfig').write_text(json.dumps(config))
PY
chmod 600 .runtime/exporter/kubeconfig
for resource in deployments.apps resourcebindings.work.karmada.io federatedhpas.autoscaling.karmada.io; do
  case "$resource" in resourcebindings*) verb=list ;; *) verb=get ;; esac
  [[ "$(kubectl --kubeconfig "$KCFG" auth can-i "$verb" "$resource" -n demo --as=system:serviceaccount:demo:karmada-lab-exporter)" == yes ]] || {
    echo "Exporter is missing $verb access to $resource in demo" >&2; exit 1;
  }
done
docker build --provenance=false -t "$IMAGE" exporter/
kind load docker-image "$IMAGE" --name karmada-mgmt
kubectl --context "$HOST" -n monitoring create secret generic karmada-lab-exporter-kubeconfig \
  --from-file=kubeconfig=.runtime/exporter/kubeconfig --dry-run=client -o yaml | kubectl --context "$HOST" apply -f -
kubectl --context "$HOST" apply -f exporter/deployment.yaml
image_id="$(docker image inspect "$IMAGE" --format '{{.Id}}')"
kubectl --context "$HOST" -n monitoring patch deployment karmada-lab-exporter --type merge \
  -p "{\"spec\":{\"template\":{\"metadata\":{\"annotations\":{\"karmada-lab.io/image-id\":\"$image_id\"}}}}}"
kubectl --context "$HOST" -n monitoring rollout status deployment/karmada-lab-exporter --timeout=180s
echo 'Exporter deployed. Verify its poll status and collected metrics separately.'
