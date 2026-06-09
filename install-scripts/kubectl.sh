#!/bin/bash
set -euo pipefail

KUBE_V="v1.33.1"
ARCH="${TARGETARCH:-amd64}"

curl -sLO "https://dl.k8s.io/release/${KUBE_V}/bin/linux/${ARCH}/kubectl"
install -m 0755 kubectl /opt/tools/bin/kubectl
rm kubectl
