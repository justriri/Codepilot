# E2B Custom Template

Use a pre-built E2B template to skip Playwright installation on every sandbox create (~1–2 min saved per run).

## What the template includes

- `/opt/agent-tools/` — verification scripts (`run_test_flow.py`, `browser_controller.py`, etc.)
- Playwright + Chromium + Firefox with OS dependencies pre-installed
- Same layout as the legacy Docker sandbox image

When `E2B_TEMPLATE_ID` is set, `SandboxManager`:

1. Creates sandboxes from your template
2. Detects `/opt/agent-tools/run_test_flow.py`
3. Skips runtime `pip install playwright` — probes engines only

## Build the template

```bash
# Install E2B CLI once
npm install -g @e2b/cli

export E2B_API_KEY=your_key
chmod +x e2b/build-template.sh
./e2b/build-template.sh
```

Default template name: `codepilot-verify` (override with `E2B_TEMPLATE_NAME`).

## Configure CodePilot

```bash
# .env
E2B_TEMPLATE_ID=codepilot-verify
BROWSER_ENGINE=auto   # will prefer chromium on template sandboxes
```

## Verify

```bash
python verify_e2b_connection.py
python test_browser_verification_e2b.py
```

`create_sandbox` should return quickly with `browser_engine: chromium` (or firefox) and no long bootstrap wait.

## Without a custom template

Leave `E2B_TEMPLATE_ID` empty. CodePilot falls back to the default E2B VM and installs Playwright at sandbox create (Firefox via auto mode).
