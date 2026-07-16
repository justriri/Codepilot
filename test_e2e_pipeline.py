"""
End-to-end pipeline validation harness.

Exercises the exact production code path (Workspace, SandboxManager,
ToolExecutor, TestRepairLoop, DebuggingAgent, generate_report) that
main.py wires together — but instead of relying on the general coding
agent to organically write a bug (non-deterministic, not a controlled
test), this script seeds a REAL, intentional bug directly, so the
debugging loop has something concrete and reproducible to catch.

This validates the workflow:

    Sandbox creates environment
        v
    Application starts
        v
    Browser testing runs
        v
    Failure is detected              <- the seeded bug causes this
        v
    DebuggingAgent analyzes the issue
        v
    Code is fixed
        v
    Tests run again
        v
    Verification report is generated

Requires: Docker running locally, and a real ANTHROPIC_API_KEY in .env
(the debugging agent makes a real Claude API call to diagnose and fix
the seeded bug).

Usage:
    python test_e2e_pipeline.py
"""

import shutil
import sys

from agent.config import load_config
from agent.workspace import Workspace
from agent.sandbox.manager import SandboxManager
from agent.agents.debugging_agent import DebuggingAgent
from agent.agents.repair_loop import TestRepairLoop
from agent.tools.executor import ToolExecutor
from agent.tools import filesystem
from providers.router import get_provider

# A dedicated workspace for this test run, kept separate from ./workspace
# (which the real agent uses) so repeated test runs never collide with
# or get confused by leftover project files from a previous session.
TEST_WORKSPACE_ROOT = "./e2e_test_workspace"

# --- The seeded bug ---
# The HTML button's real id is 'increment-btn'. The JS looks it up as
# 'incrementBtn' (a realistic, classic typo: missing hyphen / wrong
# case). getElementById returns null, and calling .addEventListener on
# null throws immediately when the script loads — so clicking the
# button silently does nothing, and a console error is emitted on page
# load. Both are exactly the kind of evidence DebuggingAgent is designed
# to reason from.

INDEX_HTML = """<!DOCTYPE html>
<html>
<head><title>Counter App</title></head>
<body>
  <h1>Counter</h1>
  <p id="count">0</p>
  <button id="increment-btn">Increment</button>
  <script src="script.js"></script>
</body>
</html>
"""

BUGGY_SCRIPT_JS = """const button = document.getElementById('incrementBtn');
const display = document.getElementById('count');
let count = 0;

button.addEventListener('click', () => {
  count = count + 1;
  display.textContent = count;
});
"""

TEST_STEPS = [
    {"action": "navigate", "path": "/"},
    {"action": "assert_visible", "selector": "#count"},
    {"action": "assert_text", "selector": "#count", "expected": "0"},
    {"action": "click", "selector": "#increment-btn"},
    {"action": "assert_text", "selector": "#count", "expected": "1"},
]


def section(title: str):
    print(f"\n{'=' * 60}\n{title}\n{'=' * 60}")


def main():
    section("STEP 0: Load config and seed the buggy project")
    config = load_config()

    # Start from a clean workspace every run, so this test is reproducible
    # regardless of what's been run before.
    shutil.rmtree(TEST_WORKSPACE_ROOT, ignore_errors=True)
    workspace = Workspace(TEST_WORKSPACE_ROOT)

    filesystem.create_file(workspace, "index.html", INDEX_HTML)
    filesystem.create_file(workspace, "script.js", BUGGY_SCRIPT_JS)
    print(f"Seeded index.html + script.js (with an intentional bug) into {workspace.root}")

    provider = get_provider(config)
    print(f"Using provider: {provider.name}")
    sandbox = SandboxManager(workspace.root, config)
    debugging_agent = DebuggingAgent(provider, workspace, config.debug_agent_max_iterations)
    repair_loop = TestRepairLoop(sandbox, debugging_agent, config.max_repair_attempts)
    executor = ToolExecutor(workspace, sandbox, config.command_timeout_s, repair_loop=repair_loop)

    try:
        section("STEP 1: Sandbox creates environment")
        result = executor.execute("create_sandbox", {})
        print(result)
        if not result.get("success"):
            print("\nFAILED at sandbox creation — is Docker running? See troubleshooting in the README.")
            sys.exit(1)

        section("STEP 2: Install dependencies (none needed for static HTML/JS)")
        result = executor.execute(
            "install_dependencies", {"command": "echo 'no dependencies needed'"}
        )
        print(result)

        section("STEP 3: Application starts")
        result = executor.execute(
            "start_application", {"command": "python3 -m http.server 3000", "port": 3000}
        )
        print(result)
        if not result.get("success"):
            print("\nFAILED to start application.")
            sys.exit(1)
        internal_url = result["internal_url"]

        section("STEP 4-7: Browser testing runs -> failure detected -> "
                "DebuggingAgent analyzes -> code fixed -> tests run again")
        print("(This single tool call internally handles the whole failure->debug->retest loop.)\n")
        result = executor.execute(
            "run_test_flow",
            {"base_url": internal_url, "steps": TEST_STEPS, "record_video": False, "timeout": 90},
        )

        print(f"\nFinal success: {result.get('success')}")
        print(f"Repair attempts used: {result.get('repair_attempts_used', 0)}")
        for step in result.get("steps", []):
            status = "PASS" if step.get("passed") else "FAIL"
            print(f"  [{status}] step {step.get('index')}: {step.get('action')} -> {step.get('detail')}")

        for entry in result.get("repair_attempts", []):
            print(f"\n  Repair attempt {entry.get('attempt')}:")
            print(f"    Explanation: {entry.get('explanation')}")
            files_touched = sorted(
                {a["input"].get("path") for a in entry.get("actions", []) if a.get("tool") == "create_file"}
            )
            print(f"    Files modified: {files_touched or 'none'}")

        section("STEP 8: Verification report is generated")
        report = executor.execute(
            "generate_verification_report",
            {"summary": "Counter app with an intentionally seeded bug, to validate the debugging loop."},
        )
        print(report.get("content", report))

        section("RESULT")
        if result.get("success"):
            print("END-TO-END PIPELINE VALIDATION: PASSED")
            print(f"(Fixed after {result.get('repair_attempts_used', 0)} repair attempt(s).)")
        else:
            print("END-TO-END PIPELINE VALIDATION: FAILED")
            print("The debugging agent did not resolve the seeded bug within the repair budget.")
            print("This is itself useful information — see the repair attempt explanations above.")

    finally:
        section("Cleanup")
        print(executor.execute("stop_application", {}))
        print(executor.execute("destroy_sandbox", {}))


if __name__ == "__main__":
    main()
