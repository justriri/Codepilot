# CodePilot E2B custom template — pre-bakes Playwright + test runner scripts.
# Build: see docs/E2B_TEMPLATE.md and e2b/build-template.sh
#
# Provisions /opt/agent-tools/ (same layout as the legacy Docker sandbox)
# so create_sandbox skips runtime Playwright installs.

FROM e2bdev/base

USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv curl procps \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/agent-tools/venv \
    && /opt/agent-tools/venv/bin/pip install --no-cache-dir playwright \
    && /opt/agent-tools/venv/bin/playwright install-deps chromium firefox \
    && /opt/agent-tools/venv/bin/playwright install chromium firefox

COPY ../sandbox/scripts/ /opt/agent-tools/

USER user
WORKDIR /home/user
