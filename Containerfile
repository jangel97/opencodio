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
        mkdir -p /opt/google-cloud-sdk; \
        exit 0; \
    fi; \
    GCLOUD_V="566.0.0"; \
    GCLOUD_URL="https://dl.google.com/dl/cloudsdk/channels/rapid/downloads/google-cloud-cli-${GCLOUD_V}-linux-x86_64.tar.gz"; \
    if [ "$TARGETARCH" = "arm64" ]; then \
        GCLOUD_URL="https://dl.google.com/dl/cloudsdk/channels/rapid/downloads/google-cloud-cli-${GCLOUD_V}-linux-arm.tar.gz"; \
    fi; \
    curl -L "$GCLOUD_URL" -o gcloud.tar.gz; \
    tar -xzf gcloud.tar.gz -C /opt;

# --- Main image ---
FROM registry.access.redhat.com/ubi10/python-312-minimal@sha256:1124c0e91dbae9b8893a218e34e7437b03865da333015078fd6bb84e2daf3665

ARG TARGETARCH
ARG ENABLE_GCLOUD="1"
USER root
ENV HOME=/home/opencodio
ENV PATH="${HOME}/.local/bin:${HOME}/.npm-global/bin:${PATH}"

# System dependencies
RUN microdnf install -y skopeo podman unzip gzip git jq nodejs nodejs-npm; \
    useradd opencodio

# OpenCode — patched binary from jangel97/opencode fork.
# Fixes JSON streaming race condition: https://github.com/anomalyco/opencode/issues/31435
# Revert to npm install once the upstream fix is merged.
COPY cli/opencode-patched /usr/local/bin/opencode
RUN chmod +x /usr/local/bin/opencode

# GCloud (optional)
COPY --from=gcloud-preparer /opt/google-cloud-sdk /opt/google-cloud-sdk
RUN set -eux; \
    if [ "$ENABLE_GCLOUD" = "1" ] && [ -f /opt/google-cloud-sdk/install.sh ]; then \
        /opt/google-cloud-sdk/install.sh -q; \
        ln -s /opt/google-cloud-sdk/bin/gcloud /usr/local/bin/gcloud; \
    fi

# Configuration
COPY conf/ ${HOME}/
COPY conf/.config/ ${HOME}/.config/
COPY scripts/stream-opencode.py entrypoint.sh /usr/local/bin/

# Permissions
RUN chown -R opencodio:0 ${HOME}; \
    chmod -R ug+rwx ${HOME}; \
    chmod +x /usr/local/bin/entrypoint.sh /usr/local/bin/stream-opencode.py

USER opencodio
WORKDIR /home/opencodio

ENTRYPOINT ["entrypoint.sh"]
