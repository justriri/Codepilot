# End-to-End Setup Checklist

This is a linear checklist for getting the full pipeline running for
real: **E2B cloud sandbox** + a live AI API key + the seeded-bug test scenario.

> **Architecture reference:** Read [docs/SANDBOX_ARCHITECTURE.md](docs/SANDBOX_ARCHITECTURE.md) first if you are debugging sandbox errors or migrating from the old Docker setup.

## 0. Audit: what's already implemented vs. what was missing

**Already implemented and verified (via mocked/logic tests, no E2B/API
needed for these):**
- Agent core (plan → act → observe loop), file tools, tool dispatch
- E2B sandbox lifecycle (create/exec/start/stop/destroy), timeouts, watchdog cleanup
- Browser automation (`BrowserController`) and step-based testing (`TestingAgent`)
- Compact + full verification reports
- `DebuggingAgent` (failure analysis, screenshot-as-image evidence,
  file-tool dispatch) and `TestRepairLoop` (bounded retry, app restart,
  exception safety) — all control-flow verified with mocks

**Sandbox runtime (requires E2B_API_KEY on your machine):**
- Real cloud sandbox creation via `Sandbox.create()`
- Command execution and file sync via E2B SDK
- Playwright test runs inside the E2B VM
- Screenshot and report generation

## 1. Configure API keys

```bash
cp .env.example .env
```

Edit `.env` and set:

```
E2B_API_KEY=...your E2B key...
DEEPSEEK_API_KEY=...your key...   # or ANTHROPIC_API_KEY / OPENAI_API_KEY
DEFAULT_MODEL=deepseek            # match your provider
```

Get an E2B key from https://e2b.dev/docs

## 2. Install Python dependencies

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## 3. Verify E2B sandbox connectivity

**Do this before anything else.** If this fails, the full pipeline will fail at `create_sandbox`.

```bash
python verify_e2b_connection.py
```

Expected output ends with:
```
E2B is correctly configured. SandboxManager will work.
```

## 4. (Optional) Verify AI provider connectivity

Fast sanity check — no sandbox required:

```bash
python test_deepseek_connection.py
```

## 5. Verify environment variables are loading

```bash
python -c "
from agent.config import load_config
c = load_config()
print('Provider:', c.default_model_provider)
print('E2B key set:', bool(c.e2b_api_key))
print('Sandbox TTL (s):', c.sandbox_ttl_s)
print('Max repair attempts:', c.max_repair_attempts)
"
```

## 6. Run the seeded-bug end-to-end test

This exercises the exact production code path (`Workspace`, `SandboxManager`,
`ToolExecutor`, `TestRepairLoop`, `DebuggingAgent`, `generate_report`).

```bash
python test_e2e_pipeline.py
```

### Expected output (abridged)

```
============================================================
STEP 1: Sandbox creates environment
============================================================
{'success': True, 'sandbox_id': '...', 'status': 'running'}

============================================================
STEP 3: Application starts
============================================================
{'success': True, 'command': 'python3 -m http.server 3000', 'port': 3000,
 'internal_url': 'http://localhost:3000', ...}

============================================================
RESULT
============================================================
END-TO-END PIPELINE VALIDATION: PASSED
```

Afterward, inspect the evidence:
```bash
ls e2e_test_workspace/.sandbox/evidence/
cat e2e_test_workspace/.sandbox/verification_report.md
```

## 7. (Optional) Run the full natural-language agent

```bash
python main.py "Build a basic web app with a button that increments a counter."
```

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `E2B_API_KEY is not set` | Missing from `.env` | Add key; run from repo root so `.env` loads |
| `E2B sandbox creation failed` | Invalid key or no quota | Check key at e2b.dev; run `verify_e2b_connection.py` |
| `DEEPSEEK_API_KEY is not set` | AI provider not configured | Set the key for your chosen `DEFAULT_MODEL` |
| `run_test_flow` → no result file | Playwright failed in E2B VM | Check runner stdout/stderr in tool result; increase timeout |
| Port exposure failed | App didn't bind to port | Read `.sandbox/app.log` via `read_file` |
| Docs mention Docker | Stale migration artifacts | Ignore Docker; see [docs/SANDBOX_ARCHITECTURE.md](docs/SANDBOX_ARCHITECTURE.md) |

## Legacy: Docker sandbox (removed from runtime)

The project previously used a local Docker image (`sandbox/Dockerfile`).
**The runtime no longer uses Docker.** The Dockerfile is kept for reference
only. Do not run `verify_docker_connection.py` — it was removed. Use
`verify_e2b_connection.py` instead.
