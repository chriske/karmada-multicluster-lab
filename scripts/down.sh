#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
clusters="$(kind get clusters)"
owned=()
for c in karmada-mgmt dc-primary dc-secondary cloud-azure; do
  if printf '%s\n' "$clusters" | grep -qx "$c"; then
    file=".runtime/kind-owned/$c.id"
    [[ -s "$file" ]] || { echo "Refusing to delete $c: no lab ownership record ($file)." >&2; exit 1; }
    current="$(docker inspect -f '{{.Id}}' "${c}-control-plane")"
    [[ "$current" == "$(cat "$file")" ]] || { echo "Refusing to delete $c: control-plane container differs from recorded lab ownership." >&2; exit 1; }
    owned+=("$c")
  fi
done
if [[ "${#owned[@]}" -eq 0 ]]; then
  echo 'No recorded lab kind clusters are running.'
  exit 0
fi
echo 'Deleting only the recorded lab kind clusters; their local PVC data will be lost.'
for c in "${owned[@]}"; do
  kind delete cluster --name "$c"
  rm -f ".runtime/kind-owned/$c.id"
done
echo 'Lab clusters deleted. Runtime kubeconfigs and downloaded artifacts remain under .runtime/.'
