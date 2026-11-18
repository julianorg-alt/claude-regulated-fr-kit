#!/usr/bin/env bash
# Installs the exact tool versions used by the kit into ./.tools/bin, verifying SHA-256.
# Linux x86_64 only (CI runners and the reference workstation). Idempotent.
set -euo pipefail

BIN_DIR="${TOOLS_DIR:-$(cd "$(dirname "$0")/.." && pwd)/.tools/bin}"
mkdir -p "$BIN_DIR"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# name version url sha256 kind(member inside archive, or "raw")
TOOLS=(
  "terraform 1.17.2 https://releases.hashicorp.com/terraform/1.17.2/terraform_1.17.2_linux_amd64.zip e6f16b2f0b137ee5729caa8c4e79a3bae4ee261acd198a1fcfa8584a6296605b zip:terraform"
  "conftest 0.71.1 https://github.com/open-policy-agent/conftest/releases/download/v0.71.1/conftest_0.71.1_Linux_x86_64.tar.gz c3f6b2a753bd56e377a1e51a95ae3e057f926f2e9139f7d5b5dfbbaf810f7985 tgz:conftest"
  "gitleaks 8.30.1 https://github.com/gitleaks/gitleaks/releases/download/v8.30.1/gitleaks_8.30.1_linux_x64.tar.gz 551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb tgz:gitleaks"
  "kind 0.33.0 https://github.com/kubernetes-sigs/kind/releases/download/v0.33.0/kind-linux-amd64 aee6151561422756b764a4ae28e7f44cda5af5a9eead3cc9985112b1de8d8e0d raw"
  "kubectl 1.37.2 https://dl.k8s.io/release/v1.37.2/bin/linux/amd64/kubectl c04487523e7aa7d1493f7808174c899db93d7a9cf57531420cd76b9bd415f8f4 raw"
  "helm 4.3.2 https://get.helm.sh/helm-v4.3.2-linux-amd64.tar.gz d1c0278d46beab79582d7e50f5b3dc206944ba8e577cde618513fd07daa53983 tgz:linux-amd64/helm"
)

want="${*:-all}"
for spec in "${TOOLS[@]}"; do
  read -r name version url sha kind <<<"$spec"
  [[ $want == all || " $want " == *" $name "* ]] || continue
  stamp="$BIN_DIR/.$name-$version"
  if [[ -x $BIN_DIR/$name && -f $stamp ]]; then continue; fi
  file="$TMP/$name.download"
  curl -fsSL --retry 3 -o "$file" "$url"
  echo "$sha  $file" | sha256sum -c --quiet -
  case $kind in
    raw) install -m 0755 "$file" "$BIN_DIR/$name" ;;
    zip:*) python3 -c "import sys,zipfile; zipfile.ZipFile(sys.argv[1]).extract(sys.argv[2], sys.argv[3])" "$file" "${kind#zip:}" "$TMP" \
             && install -m 0755 "$TMP/${kind#zip:}" "$BIN_DIR/$name" ;;
    tgz:*) tar -xzf "$file" -C "$TMP" "${kind#tgz:}" && install -m 0755 "$TMP/${kind#tgz:}" "$BIN_DIR/$name" ;;
  esac
  rm -f "$BIN_DIR"/."$name"-* && touch "$stamp"
  echo "installed $name $version"
done
