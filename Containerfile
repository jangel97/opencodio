#
# Copyright (C) 2025 Red Hat, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0

# --- Optional: gcloud SDK for Vertex AI users ---
FROM registry.access.redhat.com/ubi10@sha256:9d3b5102e7ae4f82914a1791610b75acef134b93158be6005b6ae9218c163550 as gcloud-preparer
ARG TARGETARCH
ARG ENABLE_GCLOUD="1"

RUN set -eux; \
    if [ "$ENABLE_GCLOUD" != "1" ]; then \
        mkdir -p /opt/google-cloud-sdk/bin; \
        exit 0; \
    fi; \
    GCLOUD_V="566.0.0"; \
    GCLOUD_URL="https://dl.google.com/dl/cloudsdk/channels/rapid/downloads/google-cloud-cli-${GCLOUD_V}-linux-x86_64.tar.gz"; \
    if [ "$TARGETARCH" = "arm64" ]; then \
        GCLOUD_URL="https://dl.google.com/dl/cloudsdk/channels/rapid/downloads/google-cloud-cli-${GCLOUD_V}-linux-arm.tar.gz"; \
    fi; \
    curl -L "$GCLOUD_URL" -o gcloud.tar.gz; \
    tar -xzf gcloud.tar.gz -C /opt; \
    /opt/google-cloud-sdk/install.sh -q

# --- CLI tools (git, kubectl, jq, etc.) ---
FROM registry.access.redhat.com/ubi10@sha256:9d3b5102e7ae4f82914a1791610b75acef134b93158be6005b6ae9218c163550 AS tools
ARG TARGETARCH
RUN mkdir -p /opt/tools/bin /opt/tools/lib64
COPY install-scripts/ /tmp/install-scripts/
RUN for s in /tmp/install-scripts/*.sh; do bash "$s"; done

# --- Main image: Red Hat Hardened (distroless) Python ---
FROM registry.access.redhat.com/hi/python@sha256:a9a71f12bc1767e8a0d0e157bf465cd0340e7a56c89aa89befd9b92cb09d393e

USER root
ENV HOME=/home/opencodio

# Extra CLI tools (binaries + shared libs from builder)
COPY --from=tools /opt/tools/bin/ /usr/local/bin/
COPY --from=tools /opt/tools/lib64/ /usr/lib64/

# OpenCode — patched binary from jangel97/opencode fork.
# Fixes JSON streaming race condition: https://github.com/anomalyco/opencode/issues/31435
# Revert to upstream once the fix is merged.
COPY --chmod=755 cli/opencode-patched /usr/local/bin/opencode

# GCloud (optional — builder installs when ENABLE_GCLOUD=1, otherwise empty dir)
COPY --from=gcloud-preparer /opt/google-cloud-sdk /opt/google-cloud-sdk
RUN ["/usr/bin/python3", "-c", "\nimport os\nif os.path.isfile('/opt/google-cloud-sdk/bin/gcloud'):\n    os.symlink('/opt/google-cloud-sdk/bin/gcloud', '/usr/local/bin/gcloud')\n"]

# Configuration (owned by runtime user)
COPY --chown=65532:0 conf/ ${HOME}/
COPY --chown=65532:0 conf/.config/ ${HOME}/.config/

# Scripts
COPY --chmod=755 scripts/entrypoint.py scripts/stream-opencode.py /usr/local/bin/

USER 65532
WORKDIR /home/opencodio

ENTRYPOINT ["python3", "/usr/local/bin/entrypoint.py"]
