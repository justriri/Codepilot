# Sandbox image: the isolated environment the agent's code runs AND is
# verified in.
#
# Includes Node.js + Python for the agent's own projects, plus a
# dedicated, isolated venv for Playwright (the verification harness) so
# it never conflicts with whatever Python packages the agent installs
# via install_dependencies for the project itself.

FROM node:20-bullseye

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    curl \
    procps \
    && rm -rf /var/lib/apt/lists/*

# --- Verification tooling (Playwright), isolated from the project's own deps ---
RUN python3 -m venv /opt/agent-tools/venv \
    && /opt/agent-tools/venv/bin/pip install --no-cache-dir playwright==1.47.0 \
    && /opt/agent-tools/venv/bin/playwright install --with-deps chromium

# Baked-in test tooling (browser_controller.py, testing_agent.py,
# report.py, run_test_flow.py), kept outside /workspace so it's
# unaffected by whatever the agent creates/deletes in the project
# directory. Copying the whole directory means new modules added here
# later are picked up automatically without touching this Dockerfile.
COPY scripts/ /opt/agent-tools/

WORKDIR /workspace

# Container stays alive doing nothing until the agent execs commands into it.
CMD ["sleep", "infinity"]
