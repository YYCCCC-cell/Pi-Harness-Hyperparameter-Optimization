ARG NODE_IMAGE=node@sha256:55fb5f5a527ea2c5c4a95f963e48ef90aa38c7b346054fdc8ee9957a2b55d205
ARG UBUNTU_IMAGE=ubuntu@sha256:68ee22004a9109b44973313b02ff7b1de250f1de0f5ecb628d73f579aaff33ac
FROM ${NODE_IMAGE} AS builder
ENV npm_config_audit=false npm_config_fund=false
WORKDIR /build/pi
COPY pi/ ./
RUN npm ci --ignore-scripts
# Public catalog metadata only; no API keys are supplied during image builds.
RUN npm run hydrate:model-data && npm run build:offline
COPY install-pi.mjs /build/pi/install-runtime.mjs
RUN node install-runtime.mjs
WORKDIR /build/pi-acp
COPY pi-acp/ ./
RUN npm ci --ignore-scripts && npm run build && npm prune --omit=dev --ignore-scripts

FROM ${UBUNTU_IMAGE}
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    python3 ca-certificates curl git ripgrep bash sudo procps unzip xz-utils \
    && rm -rf /var/lib/apt/lists/*
COPY --from=builder /usr/local/ /opt/benchflow/node/
COPY --from=builder /opt/pi-install/ /opt/benchflow/pi/
COPY --from=builder /build/pi-acp/dist/ /opt/benchflow/js-agents/lib/node_modules/pi-acp/dist/
COPY --from=builder /build/pi-acp/node_modules/ /opt/benchflow/js-agents/lib/node_modules/pi-acp/node_modules/
COPY --from=builder /build/pi-acp/package.json /opt/benchflow/js-agents/lib/node_modules/pi-acp/package.json
COPY --from=builder /build/pi/package-lock.json /opt/pe6203/locks/pi-build.json
COPY --from=builder /build/pi-acp/package-lock.json /opt/pe6203/locks/pi-acp.json
COPY --from=builder /opt/pi-install/package-lock.json /opt/pe6203/locks/pi-runtime.json
COPY --from=builder /build/pi/packages/ai/src/providers/data/ /opt/pe6203/model-data/
COPY runtime.json /opt/pe6203/runtime.json
COPY sandbox/ /opt/pe6203/
COPY bin/ /opt/benchflow/bin/
RUN chmod 755 /opt/benchflow/bin/* /opt/pe6203/pi_rpc_audit.py \
    && dpkg-query -W > /opt/pe6203/locks/os-packages.txt \
    && /opt/benchflow/bin/pi --version \
    && test ! -e /root/.pi && test ! -e /root/.agents && test ! -e /app/.pi
ENV PATH="/opt/benchflow/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
WORKDIR /app
CMD ["bash"]
