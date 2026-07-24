#!/usr/bin/env bash
# Build and publish the CodePilot E2B verification template.
# Requires: e2b CLI (npm i -g @e2b/cli) and E2B_API_KEY in the environment.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

TEMPLATE_NAME="${E2B_TEMPLATE_NAME:-codepilot-verify}"

echo "Building E2B template: ${TEMPLATE_NAME}"
echo "Ensure sandbox/scripts is up to date — it is copied into /opt/agent-tools/"

if ! command -v e2b >/dev/null 2>&1; then
  echo "Install the E2B CLI: npm install -g @e2b/cli"
  exit 1
fi

# Stage scripts beside Dockerfile for COPY
rm -rf e2b/staged-scripts
cp -R sandbox/scripts e2b/staged-scripts

cat > e2b/Dockerfile.build <<'DOCKER'
FROM e2bdev/base
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv curl procps \
    && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv /opt/agent-tools/venv \
    && /opt/agent-tools/venv/bin/pip install --no-cache-dir playwright \
    && /opt/agent-tools/venv/bin/playwright install-deps chromium firefox \
    && /opt/agent-tools/venv/bin/playwright install chromium firefox
COPY staged-scripts/ /opt/agent-tools/
USER user
WORKDIR /home/user
DOCKER

cd e2b
e2b template build --name "$TEMPLATE_NAME" --dockerfile Dockerfile.build

echo ""
echo "Template built. Set in .env:"
echo "  E2B_TEMPLATE_ID=${TEMPLATE_NAME}"
echo ""
echo "Sandboxes will use /opt/agent-tools/ and skip runtime Playwright install."
