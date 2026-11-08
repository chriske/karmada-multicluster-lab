#!/usr/bin/env bash
# Required part of the DEFAULT bootstrap: metrics-server -> Karmada metrics-adapter -> FederatedHPA.
# Uses pinned official manifests/helper. Runtime integration still needs validation on WSL2/kind.
set -euo pipefail
cd "$(dirname "$0")/.."
: "${KARMADA_VERSION:=v1.19.1}"
: "${METRICS_SERVER_VERSION:=v0.8.0}"

for exe in git kubectl openssl python3; do
  command -v "$exe" >/dev/null || { echo "Required binary not found: $exe" >&2; exit 1; }
done
HOSTCFG="$(realpath .runtime/freelens/karmada-mgmt.yaml)"
KARMADA_CFG="$(realpath .runtime/karmada/karmada-apiserver.config)"
[[ -s "$HOSTCFG" && -s "$KARMADA_CFG" ]] || {
  echo 'Missing management or Karmada kubeconfig; run make kind-up and make karmada-up first.' >&2; exit 1;
}

# Render the official tagged release overlay locally. This avoids fetching the
# GitHub release asset separately for every member and pins its source commit.
[[ "$METRICS_SERVER_VERSION" == v0.8.0 ]] || { echo 'Unsupported metrics-server version; update the pinned source commit as well.' >&2; exit 1; }
METRICS_SRC="$PWD/.runtime/metrics-server-source"
if [[ ! -d "$METRICS_SRC/.git" ]]; then
  git clone --depth 1 --branch "$METRICS_SERVER_VERSION" https://github.com/kubernetes-sigs/metrics-server.git "$METRICS_SRC"
fi
[[ "$(git -C "$METRICS_SRC" rev-parse HEAD)" == d66279c6426c6581d9656fe3d42bc52db7c29597 ]] || { echo 'Unexpected metrics-server source revision.' >&2; exit 1; }
git -C "$METRICS_SRC" diff --quiet -- manifests || { echo 'metrics-server manifests have local changes; refusing install.' >&2; exit 1; }
kubectl kustomize "$METRICS_SRC/manifests/overlays/release" > .runtime/metrics-server-components.yaml

for c in dc-primary dc-secondary cloud-azure; do
  CTX="kind-$c"
  echo "=== Installing metrics-server ${METRICS_SERVER_VERSION} into ${c} ==="
  kubectl --context "$CTX" apply -f .runtime/metrics-server-components.yaml
  # kind's node kubelet serving certificate is usually not trusted by metrics-server.
  # Do not duplicate the flag on repeated runs.
  args="$(kubectl --context "$CTX" -n kube-system get deployment metrics-server -o jsonpath='{.spec.template.spec.containers[0].args[*]}')"
  if [[ " $args " != *' --kubelet-insecure-tls '* ]]; then
    kubectl --context "$CTX" -n kube-system patch deployment metrics-server --type=json \
      -p='[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'
  fi
  kubectl --context "$CTX" -n kube-system rollout status deployment/metrics-server --timeout=180s
  ok=0
  for try in $(seq 1 30); do
    if kubectl --context "$CTX" top nodes >/dev/null 2>&1; then ok=1; break; fi
    sleep 5
  done
  [[ "$ok" -eq 1 ]] || { echo "metrics.k8s.io not usable in ${c}; inspect metrics-server pod logs and kubelet connectivity" >&2; exit 1; }
  echo "metrics-server API: ready in ${c}"
done

echo '=== Installing the Karmada metrics adapter using pinned official source ==='
# karmadactl init creates the adapter kubeconfig secret, but the upstream
# deployment helper expects a separate serving-certificate secret.
CERT_DIR="$(mktemp -d .runtime/metrics-adapter-cert.XXXXXX)"
chmod 700 "$CERT_DIR"
trap 'rm -rf "$CERT_DIR"' EXIT
existing_secret="$(kubectl --kubeconfig "$HOSTCFG" --context kind-karmada-mgmt -n karmada-system get secret karmada-metrics-adapter-cert --ignore-not-found -o json)"
reuse_cert=0
if [[ -n "$existing_secret" ]]; then
  if printf '%s' "$existing_secret" | python3 -c '
import base64, json, pathlib, sys
data = json.load(sys.stdin)["data"]
target = pathlib.Path(sys.argv[1])
for name in ("tls.crt", "tls.key"):
    (target / name).write_bytes(base64.b64decode(data[name], validate=True))
' "$CERT_DIR" && \
     openssl verify -CAfile .runtime/karmada/pki/ca.crt -verify_hostname karmada-metrics-adapter.karmada-system.svc "$CERT_DIR/tls.crt" >/dev/null && \
     openssl x509 -in "$CERT_DIR/tls.crt" -noout -checkend 604800 >/dev/null && \
     cmp -s <(openssl x509 -in "$CERT_DIR/tls.crt" -pubkey -noout) <(openssl pkey -in "$CERT_DIR/tls.key" -pubout); then
    reuse_cert=1
  fi
fi
if [[ "$reuse_cert" -eq 0 ]]; then
openssl req -new -newkey rsa:2048 -nodes -keyout "$CERT_DIR/tls.key" -out "$CERT_DIR/request.csr" \
  -subj '/CN=karmada-metrics-adapter.karmada-system.svc' >/dev/null 2>&1
printf '%s\n' 'subjectAltName=DNS:karmada-metrics-adapter.karmada-system.svc,DNS:karmada-metrics-adapter.karmada-system.svc.cluster.local' 'extendedKeyUsage=serverAuth' > "$CERT_DIR/extensions"
openssl x509 -req -in "$CERT_DIR/request.csr" -CA .runtime/karmada/pki/ca.crt -CAkey .runtime/karmada/pki/ca.key \
  -set_serial "0x$(openssl rand -hex 16)" -days 365 -sha256 -extfile "$CERT_DIR/extensions" -out "$CERT_DIR/tls.crt" >/dev/null 2>&1
kubectl --kubeconfig "$HOSTCFG" --context kind-karmada-mgmt -n karmada-system create secret generic karmada-metrics-adapter-cert \
  --from-file=ca.crt=.runtime/karmada/pki/ca.crt --from-file=tls.crt="$CERT_DIR/tls.crt" --from-file=tls.key="$CERT_DIR/tls.key" \
  --dry-run=client -o yaml | kubectl --kubeconfig "$HOSTCFG" --context kind-karmada-mgmt apply -f -
else
  echo 'Reusing valid metrics-adapter serving certificate.'
fi
SRC="$(realpath -m .runtime/karmada-source)"
if [[ ! -d "$SRC/.git" ]]; then
  git clone --depth 1 --branch "$KARMADA_VERSION" https://github.com/karmada-io/karmada.git "$SRC"
fi
actual="$(git -C "$SRC" describe --tags --exact-match 2>/dev/null || true)"
[[ "$actual" == "$KARMADA_VERSION" ]] || {
  echo "Pinned Karmada source must be ${KARMADA_VERSION}, found '${actual:-unknown}'. Fix ${SRC}." >&2; exit 1;
}
# The upstream tagged helper applies a manifest containing :latest. Render a
# version-pinned copy locally before invoking the official helper.
python3 - "$SRC/artifacts/deploy/karmada-metrics-adapter.yaml" "$KARMADA_VERSION" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
content = path.read_text()
base = 'docker.io/karmada/karmada-metrics-adapter:'
expected = base + sys.argv[2]
if base + 'latest' in content:
    content = content.replace(base + 'latest', expected)
elif expected not in content:
    raise SystemExit('Unexpected upstream metrics-adapter image; refusing an unpinned install')
path.write_text(content)
PY
# The helper sources a development utility that calls Go only to populate an
# unrelated minimum-version variable. Read the same value from go.mod instead;
# installing the adapter does not otherwise require the Go compiler.
python3 - "$SRC/hack/util.sh" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
content = path.read_text()
original = 'MIN_GO_VERSION="go$(go list -m -f {{.GoVersion}})"'
replacement = 'MIN_GO_VERSION="go$(awk \'$1 == "go" {print $2; exit}\' "${REPO_ROOT}/go.mod")"'
if original in content:
    content = content.replace(original, replacement, 1)
elif replacement not in content:
    raise SystemExit('Unexpected upstream util.sh; cannot remove adapter helper Go dependency')
path.write_text(content)
PY
CTX="$(kubectl --kubeconfig "$KARMADA_CFG" config current-context)"
[[ -n "$CTX" ]] || { echo 'No Karmada API kubeconfig context' >&2; exit 1; }
(
  cd "$SRC"
  bash hack/deploy-metrics-adapter.sh "$HOSTCFG" kind-karmada-mgmt "$KARMADA_CFG" "$CTX"
)
"$(dirname "$0")/verify-fhpa-prereqs.sh"
