#!/usr/bin/env bash
# Karmada Hybrid Cloud Lab - WSL2 Ubuntu CLI bootstrap
# Tested for Bash syntax only. Run interactively inside Ubuntu WSL2.
# Docker Desktop must be installed/enabled separately on Windows.
set -Eeuo pipefail

if [[ "$(uname -s)" != "Linux" || "$(uname -m)" != "x86_64" ]]; then
  echo 'This installer is intended for x86_64 Linux (Ubuntu under WSL2).' >&2
  exit 1
fi
if ! command -v apt-get >/dev/null 2>&1; then
  echo 'APT not found. This installer assumes Ubuntu/Debian.' >&2
  exit 1
fi

KIND_VERSION=v0.33.0
KUBECTL_VERSION=v1.35.9
HELM_VERSION=v3.22.1
KARMADA_VERSION=v1.19.1
YQ_VERSION=v4.54.2

sudo apt-get update
sudo apt-get install -y \
  ca-certificates curl wget git make jq \
  python3 python3-venv python3-pip \
  bash tar gzip unzip zip openssl gettext-base \
  dnsutils iproute2 iputils-ping netcat-openbsd procps lsof gnupg

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# kubectl: verify published Kubernetes SHA-256.
curl -fsSL "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/amd64/kubectl" -o "$TMP/kubectl"
curl -fsSL "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/amd64/kubectl.sha256" -o "$TMP/kubectl.sha256"
printf '%s  %s\n' "$(cat "$TMP/kubectl.sha256")" "$TMP/kubectl" | sha256sum -c -
sudo install -m 0755 "$TMP/kubectl" /usr/local/bin/kubectl

# kind: official release binary.
curl -fsSL "https://kind.sigs.k8s.io/dl/${KIND_VERSION}/kind-linux-amd64" -o "$TMP/kind"
sudo install -m 0755 "$TMP/kind" /usr/local/bin/kind

# Helm 3: verify checksum published for v3.22.1 linux-amd64.
curl -fsSL "https://get.helm.sh/helm-${HELM_VERSION}-linux-amd64.tar.gz" -o "$TMP/helm.tgz"
printf '%s  %s\n' \
  '896cf63684a42a723d61c980369d6e588330927deb13676ca0d85006dd6da0ea' \
  "$TMP/helm.tgz" | sha256sum -c -
tar -xzf "$TMP/helm.tgz" -C "$TMP" linux-amd64/helm
sudo install -m 0755 "$TMP/linux-amd64/helm" /usr/local/bin/helm

# Karmada v1.19.1 release binaries: verify upstream-provided sha256 archives.
for tool in karmadactl kubectl-karmada; do
  base="https://github.com/karmada-io/karmada/releases/download/${KARMADA_VERSION}/${tool}-linux-amd64.tgz"
  curl -fsSL "$base" -o "$TMP/${tool}.tgz"
  curl -fsSL "${base}.sha256" -o "$TMP/${tool}.sha256"
  expected="$(awk 'NR==1 { print $1 }' "$TMP/${tool}.sha256")"
  printf '%s  %s\n' "$expected" "$TMP/${tool}.tgz" | sha256sum -c -
  mkdir -p "$TMP/$tool"
  tar -xzf "$TMP/${tool}.tgz" -C "$TMP/$tool"
  if [[ ! -f "$TMP/$tool/$tool" ]]; then
    echo "Cannot locate $tool in release archive." >&2
    exit 1
  fi
  sudo install -m 0755 "$TMP/$tool/$tool" "/usr/local/bin/$tool"
done

# yq: optional but recommended YAML diagnostics helper.
curl -fsSL "https://github.com/mikefarah/yq/releases/download/${YQ_VERSION}/yq_linux_amd64" -o "$TMP/yq"
sudo install -m 0755 "$TMP/yq" /usr/local/bin/yq

printf '\nInstalled tool versions:\n'
kind version
kubectl version --client
helm version --short
karmadactl version --client 2>/dev/null || karmadactl version || true
yq --version
printf '\nDocker Desktop integration (not installed by this script):\n'
if command -v docker >/dev/null 2>&1; then
  docker version --format '{{.Client.Version}}' || true
  docker info --format 'Server: {{.ServerVersion}}' || true
else
  echo 'docker command missing: enable Docker Desktop > Settings > Resources > WSL Integration.'
fi
printf '\nDone. Run inside the unpacked lab repo: make verify-names\n'
