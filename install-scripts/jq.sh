#!/bin/bash
set -euo pipefail

JQ_V="1.7.1"
ARCH="${TARGETARCH:-amd64}"
JQ_ARCH="amd64"
if [ "$ARCH" = "arm64" ]; then JQ_ARCH="arm64"; fi

curl -sL "https://github.com/jqlang/jq/releases/download/jq-${JQ_V}/jq-linux-${JQ_ARCH}" -o /opt/tools/bin/jq
chmod +x /opt/tools/bin/jq
