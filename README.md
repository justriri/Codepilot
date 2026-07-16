# AI Coding Agent — Core + Sandbox + Browser Testing + Autonomous Debugging (MVP)

CodePilot provides AI coding agents with isolated sandbox environments to run applications, execute codes, test changes end-to-end, capture proof of results, and generate verification reports, helping developers confidently trust AI-generated code without manual testing.

## Architecture

```
User Request
     │
     ▼
AgentController (plan → act → observe → verify loop)
     │
     ├──▶ ClaudeClient ──▶ Anthropic API
     │
     └──▶ ToolExecutor
              │
              ├─ create_file / read_file / list_files ──▶ Workspace (host dir)
              │                                                │
              │                                    bind-mounted at /workspace
              │                                                ▼
              │                                       ┌─────────────────────┐
              ├─ create_sandbox / install_dependencies │  Docker container   │
              │  / run_command / start_application /   │  (isolated)         │
              │  stop_application / destroy_sandbox ──▶ │  /opt/agent-tools/  │
              │                                          │  ├ browser_controller│
              │                                          │  ├ testing_agent     │
              │                                          │  ├ report            │
              │                                          │  └ run_test_flow     │
              │                                          └─────────────────────┘
              │
              └─ run_test_flow ──▶ TestRepairLoop (agent/agents/repair_loop.py)
                                        │
                                        ├─ sandbox.run_test_flow()  (as above)
                                        │
                                        ├─ if failed ──▶ DebuggingAgent (HOST-SIDE)
                                        │                agent/agents/debugging_agent.py
                                        │                ├─ own Claude call, own system prompt
                                        │                ├─ reads failed steps + logs +
                                        │                │  screenshots (as real images)
                                        │                └─ reuses read_file/list_files/
                                        │                   create_file directly
                                        │
                                        ├─ restart the app (so the fix actually loads)
                                        │
                                        └─ retest — up to max_repair_attempts (hard cap)
              │
              └─ generate_verification_report ──▶ SandboxManager.generate_report()
```

**Why the Debugging Agent runs on the host, not in the container:** it
needs the Anthropic API key, which should never be exposed inside the
sandbox the agent's own generated code executes in. It reuses
`agent/tools/filesystem.py` directly — not the full `ToolExecutor` —
specifically to avoid a circular construction dependency (`ToolExecutor`
needs the repair loop, which needs the debugging agent; if the debugging
agent also needed `ToolExecutor`, nothing could be constructed first).

**Why the retry loop is plain Python, not LLM judgment:** the workflow
this replaces was "the general coding agent notices a failure and
decides to retry" — informal and unbounded. `TestRepairLoop` enforces
`max_repair_attempts` (default 3) in code, so a bug the debugging agent
can never actually fix cannot cause an infinite loop — verified directly
(see "Testing this locally" below).

**What did NOT need to change to add this:** `run_test_flow`'s tool
input/output contract, `agent/tools/definitions.py`'s schema,
`ToolExecutor`'s registry, `sandbox/scripts/*`, and `sandbox/Dockerfile`
are all unchanged. From the general coding agent's perspective,
`run_test_flow` just quietly does more work now and comes back more
reliable.

## Project Structure

```
agent_mvp/
├── main.py                            # wires everything together
├── sandbox/
│   ├── Dockerfile                       # unchanged by the debugging loop
│   └── scripts/                          # unchanged by the debugging loop
│       ├── browser_controller.py          # open_browser/click_element/fill_input/
│       │                                    # take_screenshot/close_browser
│       ├── testing_agent.py                # executes ordered test steps
│       ├── report.py                        # compact Application/Status/... format
│       └── run_test_flow.py                  # thin CLI wiring the 3 above together
├── agent/
│   ├── config.py                        # + max_repair_attempts, debug_agent_max_iterations
│   ├── workspace.py
│   ├── claude_client.py
│   ├── controller.py                     # system prompt updated: trust run_test_flow's
│   │                                       # own repair attempts rather than re-looping
│   ├── agents/                            # NEW — LLM-driven agent roles
│   │   ├── __init__.py
│   │   ├── debugging_agent.py               # NEW — failure analysis + code repair
│   │   └── repair_loop.py                    # NEW — bounded retry orchestration
│   ├── sandbox/
│   │   └── manager.py                     # + port stored on start_application,
│   │                                       # + repair attempts section in generate_report()
│   └── tools/
│       ├── definitions.py                 # run_test_flow description updated (schema same)
│       ├── executor.py                     # + optional repair_loop, delegates run_test_flow
│       ├── filesystem.py                    # unchanged — reused directly by DebuggingAgent
│       ├── sandbox_tools.py
│       └── shell.py                          # deprecated, unused
├── requirements.txt
├── .env.example                           # + MAX_REPAIR_ATTEMPTS, DEBUG_AGENT_MAX_ITERATIONS
└── workspace/                               # created automatically at runtime
```

## 1. Failure Analysis — `DebuggingAgent`

`agent/agents/debugging_agent.py`. Given a failed `run_test_flow` result,
it assembles a multi-part message for Claude containing:

- **Failed test steps** — action, selector, and the `detail` explaining what went wrong
- **Error logs** — browser console errors, plus the tail of `.sandbox/app.log`
- **Browser errors** — the runner's own top-level error, if the test process itself crashed
- **Screenshots, if available** — attached as **real images** (base64, Claude's native
  vision input) for every failed step that has one, so the model can actually
  see the broken page, not just read selector names
- **Relevant project files** — not pre-stuffed into the prompt; instead the
  agent gets its own small tool loop (`list_files`, `read_file`) to inspect
  whatever it decides is relevant

It then applies a fix via `create_file` and stops once confident, returning
a plain-language root-cause explanation plus a log of every file it touched.

## 2. Code Repair

The same `DebuggingAgent` tool loop handles this — `read_file` to inspect,
`create_file` to overwrite with the corrected content. It's given **only**
these 3 file tools (reused unchanged from `agent/tools/filesystem.py`) —
deliberately no access to `create_sandbox`/`install_dependencies`/etc., since
its job is a targeted fix, not general project construction.

## 3. Retry Loop — `TestRepairLoop`

`agent/agents/repair_loop.py`:

```
Test
  ↓
Failure detected
  ↓
DebuggingAgent.analyze_and_fix()
  ↓
Restart the application       (a code fix does nothing to an already-running process)
  ↓
Test again
  ↓
... up to max_repair_attempts (default 3, hard cap enforced in Python)
```

If nothing was ever started via `start_application` (e.g. a static-file
check), the restart step is safely skipped. If the debugging agent's own
API call fails, the loop stops gracefully rather than crashing the whole
tool call. Both were verified directly — see below.

## 4. Integration

```
Agent
 → Sandbox Manager        (create_sandbox → install_dependencies → start_application)
 → Testing Agent            (run_test_flow: browser opens app, steps run, evidence captured)
 → Debugging Agent            (ONLY if a step failed)
 → Testing Agent again          (same steps, re-tested after the fix + restart)
 → ... repeats up to 3 times
 → Reports                        (generate_verification_report, now includes repair attempts)
```

## Installation

No new dependencies — the debugging agent reuses the existing Anthropic
API client and file tools:

```bash
cd agent_mvp
docker build -t agent-sandbox:latest ./sandbox   # unchanged from before, no rebuild needed
                                                    # unless you haven't built it yet
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add your ANTHROPIC_API_KEY
```

New optional settings in `.env` (defaults shown):
```
MAX_REPAIR_ATTEMPTS=3
DEBUG_AGENT_MAX_ITERATIONS=6
```

## Running the agent

```bash
python main.py "Build a signup page with an email field and submit button. On submit, show a welcome message — but introduce a small bug on purpose to see the debugging loop work."
```

Or more realistically, just run any normal request — if `run_test_flow`
happens to fail, you'll see something like:
```
[tool call] run_test_flow({...})
# internally: initial test fails, DebuggingAgent reads server.js, finds a typo,
# rewrites the file, app is restarted, test re-runs and passes
[tool result] {"success": true, "steps": [...], "repair_attempts": [{"attempt": 1, "success": true, "explanation": "..."}], "repair_attempts_used": 1}
[tool call] generate_verification_report({...})
```

The generated `.sandbox/verification_report.md` will include a
**"Debugging Agent Repair Attempts"** section listing each attempt's
explanation and which files were modified.

## Testing this locally

All of the following were actually run during development — not just
described:

**`DebuggingAgent`'s file-tool dispatch and evidence assembly** (no API
calls needed for this part):
```bash
python -c "
from agent.workspace import Workspace
from agent.claude_client import ClaudeClient
from agent.agents.debugging_agent import DebuggingAgent

ws = Workspace('/tmp/debug_test')
debugger = DebuggingAgent(ClaudeClient('dummy-key', 'x'), ws, max_iterations=6)
print(debugger._execute_tool('list_files', {}))
"
```

**`TestRepairLoop`'s control flow**, with a fake sandbox and a fake
debugging agent (no Docker, no API calls, pure logic):
```bash
python -c "
from agent.agents.repair_loop import TestRepairLoop

class FakeSandbox:
    def __init__(self):
        self.last_start_result = {'success': True, 'command': 'node server.js', 'port': 3000}
        self.run_calls = 0
    def run_test_flow(self, base_url, steps, record_video, timeout):
        self.run_calls += 1
        return {'success': self.run_calls >= 3, 'steps': [], 'console_errors': []}
    def stop_application(self): return {'success': True}
    def start_application(self, command, port): return {'success': True}

class FakeDebugger:
    def analyze_and_fix(self, test_result):
        return {'success': True, 'explanation': 'fixed it', 'actions': []}

loop = TestRepairLoop(FakeSandbox(), FakeDebugger(), max_repair_attempts=3)
result = loop.run({'base_url': 'http://localhost:3000', 'steps': []})
print(result['success'], result['repair_attempts_used'])   # True 2
"
```

**Confirming the hard cap actually stops** (the property that matters
most — an unfixable bug must not loop forever):
```bash
python -c "
from agent.agents.repair_loop import TestRepairLoop

class AlwaysFails:
    def __init__(self):
        self.last_start_result = None
        self.run_calls = 0
    def run_test_flow(self, base_url, steps, record_video, timeout):
        self.run_calls += 1
        return {'success': False, 'steps': [], 'console_errors': []}
    def stop_application(self): return {'success': True}
    def start_application(self, command, port): return {'success': True}

class NeverFixes:
    def analyze_and_fix(self, test_result):
        return {'success': False, 'explanation': 'no idea', 'actions': []}

sandbox = AlwaysFails()
loop = TestRepairLoop(sandbox, NeverFixes(), max_repair_attempts=3)
result = loop.run({'base_url': 'http://localhost:3000', 'steps': []})
print('run_calls:', sandbox.run_calls)  # exactly 4: 1 initial + 3 capped retries, not infinite
"
```

## Safety

Everything from earlier phases (resource limits, capability drops,
timeouts, sandbox watchdog cleanup) is unchanged. New to this phase:

- **Hard repair cap** (`max_repair_attempts`, default 3) enforced in
  plain Python — not left to either LLM's discretion.
- **Debugging agent exceptions can't crash the tool call** — if the
  debugging LLM call itself fails (e.g. an API error), the loop stops
  and returns the last known, properly-structured test result rather
  than propagating a raw exception.
- **API key isolation** — the debugging agent runs entirely on the host;
  the sandbox container never has network access to Anthropic's API or
  any credential.
- **Restart-if-running, skip-if-not** — the repair loop only restarts
  the application when one was actually started successfully; a static-
  file test scenario doesn't trigger a spurious restart.

**Known simplification, documented not hidden:** repeated repair
attempts overwrite the same screenshot filenames rather than keeping a
per-attempt evidence history — the evidence reflects only the latest
attempt. Preserving the full trail would need a small, backward-compatible
addition to `sandbox/scripts/run_test_flow.py` (an optional
`evidence_subdir` per attempt); deliberately deferred since this round's
instructions were to avoid touching `sandbox/scripts/`.

## What this MVP does and does not do

**Does:**
- Automatically detects test failures and invokes a dedicated debugging
  role — not just the general coding agent looping informally
- Gives the debugging agent real visual evidence (actual screenshot
  images, not just text) alongside logs and structured failure detail
- Applies fixes and **restarts the application** before retesting, so a
  fix is actually verified against a live process, not a stale one
- Hard-caps retries in code (verified: an unfixable bug stops at exactly
  `max_repair_attempts`, confirmed not to loop forever)
- Required zero changes to the tool-calling contract the general coding
  agent uses — verified directly, not just claimed
- Surfaces the full repair history in the final verification report

**Does not yet:**
- Per-attempt evidence preservation (see "Known simplification" above)
- A way for the debugging agent to say "I need to see file X that isn't
  in the project" beyond its own `list_files`/`read_file` loop (which
  already covers this, but it can't inspect anything outside the
  workspace, e.g. system-level Docker/network diagnostics)
- Escalation back to the general coding agent with a structured "here's
  what I tried and couldn't fix" handoff — today it's reported via the
  verification report, but the calling agent doesn't get a specially
  formatted signal to reason further beyond the report text itself
- A persistence layer or web UI — reports and repair history exist as
  files (`.sandbox/verification_report.md`), not a queryable record
