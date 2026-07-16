# End-to-End Setup Checklist

This is a linear checklist for getting the full pipeline running for
real: Docker + a live Anthropic API key + the seeded-bug test scenario.

## 0. Audit: what's already implemented vs. what was missing

**Already implemented and verified (via mocked/logic tests, no Docker/API
needed for these):**
- Agent core (plan → act → observe loop), file tools, tool dispatch
- Docker sandbox lifecycle (create/exec/start/stop/destroy), resource
  limits, timeouts, watchdog cleanup
- Browser automation (`BrowserController`) and step-based testing
  (`TestingAgent`) baked into the sandbox image
- Compact + full verification reports
- `DebuggingAgent` (failure analysis, screenshot-as-image evidence,
  file-tool dispatch) and `TestRepairLoop` (bounded retry, app restart,
  exception safety) — all control-flow verified with mocks

**Gaps found and fixed during this audit (this is what was actually
missing for a real run):**
1. **Invalid default model string.** `AGENT_MODEL` defaulted to
   `claude-sonnet-4-6`, which isn't a real model — every API call would
   have failed immediately. Fixed to `claude-sonnet-5` in both
   `agent/config.py` and `.env.example`.
2. **No error handling around the main agent loop's API call.** An
   invalid API key (or any Anthropic API error) would crash `main.py`
   with a raw traceback instead of a clean message. Fixed in
   `agent/controller.py` — verified with a mocked `AuthenticationError`.
   (Note: `TestRepairLoop` already handled this correctly for the
   debugging agent's own API calls — this fix brings the main loop up
   to the same standard.)

**Still requires your machine to actually validate (cannot be tested in
this environment — no Docker daemon, no API key available here):**
- The real Docker build (Chromium/Playwright download)
- Real container creation, exec, and port mapping
- The real Claude API call inside `DebuggingAgent.analyze_and_fix`
- The real Playwright browser run inside the container

## 1. Configure the Claude API key

```bash
cd agent_mvp
cp .env.example .env
```

Edit `.env` and set:
```
ANTHROPIC_API_KEY=sk-ant-...your real key...
```

Get a key from the Anthropic Console if you don't have one. The debugging
agent makes its own, separate API calls (on top of the main agent loop),
so budget for that — a run with 1-2 repair attempts roughly doubles the
API calls compared to a bug-free run.

## 2. Configure Docker

Install Docker Desktop (Mac/Windows) or `dockerd` (Linux), then confirm:
```bash
docker info
```
should print daemon info, not an error. If this fails, nothing past
`create_sandbox` will work — this is the most common blocker.

Build the sandbox image (this downloads Chromium — the first build can
take several minutes):
```bash
docker build -t agent-sandbox:latest ./sandbox
```

Confirm it exists:
```bash
docker images | grep agent-sandbox
```

## 3. Install Python dependencies

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## 4. Verify environment variables are actually loading

```bash
python -c "
from agent.config import load_config
c = load_config()
print('Model:', c.model)
print('Docker image:', c.docker_image)
print('Max repair attempts:', c.max_repair_attempts)
print('API key set:', bool(c.anthropic_api_key) and c.anthropic_api_key != 'your_api_key_here')
"
```
Expected output:
```
Model: claude-sonnet-5
Docker image: agent-sandbox:latest
Max repair attempts: 3
API key set: True
```
If `API key set: False` or it raises `RuntimeError`, your `.env` isn't
being picked up — check you're running from the `agent_mvp/` directory
and that `.env` (not `.env.example`) has your real key.

## 5. Run the seeded-bug end-to-end test

This is the controlled validation scenario: a real counter app with a
real, deliberately seeded bug (an `id` mismatch between the HTML button
and the JS `getElementById` call — a realistic typo, not a contrived
one), run through the exact production code path `main.py` uses.

```bash
python test_e2e_pipeline.py
```

### Expected output (abridged)

```
============================================================
STEP 0: Load config and seed the buggy project
============================================================
Seeded index.html + script.js (with an intentional bug) into .../e2e_test_workspace

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
STEP 4-7: Browser testing runs -> failure detected -> DebuggingAgent
analyzes -> code fixed -> tests run again
============================================================
Final success: True
Repair attempts used: 1
  [PASS] step 0: navigate -> Opened http://localhost:3000/ (status 200)
  [PASS] step 1: assert_visible -> Element is visible
  [PASS] step 2: assert_text -> Got '0', expected it to contain '0'
  [PASS] step 3: click -> Clicked '#increment-btn'
  [PASS] step 4: assert_text -> Got '1', expected it to contain '1'

  Repair attempt 1:
    Explanation: [Claude's real explanation of the id-mismatch bug and its fix]
    Files modified: ['script.js']

============================================================
STEP 8: Verification report is generated
============================================================
[full Markdown report content]

============================================================
RESULT
============================================================
END-TO-END PIPELINE VALIDATION: PASSED
(Fixed after 1 repair attempt(s).)
```

The exact wording of the debugging agent's explanation will vary (it's a
real LLM call) — what matters is: step 4 fails on the first test run,
`repair_attempts_used` is 1 (not 0, not 3), `script.js` is listed as
modified, and the final result is `PASSED`.

Afterward, inspect the evidence directly:
```bash
ls e2e_test_workspace/.sandbox/evidence/
cat e2e_test_workspace/.sandbox/verification_report.md
cat e2e_test_workspace/script.js   # should now say 'increment-btn', not 'incrementBtn'
```

## 6. (Optional) Run the full natural-language agent

This exercises the complete, open-ended pipeline — but whether the
debugging loop actually triggers depends on whether Claude happens to
write a bug on its own first try, which is non-deterministic. Use this
to validate the *overall* experience, and `test_e2e_pipeline.py` above
to reliably validate the *debugging loop specifically*.

```bash
python main.py "Build a basic web app with a button that increments a counter."
```

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Could not connect to Docker: ... Is Docker running?` | Docker daemon not running | Start Docker Desktop / `sudo systemctl start docker` |
| `Failed to create sandbox: 404 Client Error ... No such image` | Sandbox image not built yet | `docker build -t agent-sandbox:latest ./sandbox` |
| `ANTHROPIC_API_KEY is not set` | `.env` missing or not in cwd | Run from `agent_mvp/`; confirm `.env` exists (not just `.env.example`) |
| `Authentication with the Anthropic API failed` | Invalid/expired key | Check the key value in `.env`, no extra quotes/whitespace |
| `run_test_flow` result has `"error": "Test runner did not produce a result file..."` | Playwright/Chromium failed inside the container | `docker exec` into a running container and check `/opt/agent-tools/venv/bin/playwright --version`; rebuild the image if corrupted |
| Container port has no host mapping | App failed to bind the port | Read `.sandbox/app.log` via `read_file` — usually a startup error in the app itself |
| Everything passes on attempt 1, no repair attempts shown | Working as intended — no bug to fix | This is the expected happy path when running the *unmodified* natural-language agent; use `test_e2e_pipeline.py` to reliably see the debugging loop |
| Script hangs at `STEP 4-7` for a long time | `SANDBOX_TTL_S`/timeouts may need tuning, or Chromium is slow to start under low resources | Bump `SANDBOX_MEM_LIMIT` in `.env`; check `docker stats` while it runs |
