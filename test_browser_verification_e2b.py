"""
Direct test of browser verification on E2B — no AI agent required.

Exercises the fixed path:
  create sandbox -> seed HTML -> start server -> run_test_flow -> report
"""

import os
import shutil
import textwrap

from agent.config import load_config
from agent.sandbox.manager import SandboxManager
from agent.tools.executor import ToolExecutor
from agent.workspace import Workspace

TEST_DIR = "./browser_verify_test_workspace"

HTML = textwrap.dedent("""
<!DOCTYPE html>
<html>
<head><title>CodePilot Test</title></head>
<body>
  <h1>CodePilot Test</h1>
  <p id="status">Waiting...</p>
  <button id="verifyBtn" onclick="document.getElementById('status').textContent='Success!'">Click Me</button>
</body>
</html>
""").strip()


def main():
    if os.path.isdir(TEST_DIR):
        shutil.rmtree(TEST_DIR)

    config = load_config()
    workspace = Workspace(TEST_DIR)
    sandbox = SandboxManager(workspace.root, config)
    executor = ToolExecutor(workspace, sandbox, config.command_timeout_s)

    steps = [
        ("create_sandbox", {}),
        ("create_file", {"path": "index.html", "content": HTML}),
        ("start_application", {"command": "python3 -m http.server 3000", "port": 3000}),
    ]

    for name, inp in steps:
        print(f"\n--- {name} ---")
        result = executor.execute(name, inp)
        print(result)
        if not result.get("success", True) and result.get("error"):
            print(f"FAILED at {name}")
            executor.execute("destroy_sandbox", {})
            return 1

    start = sandbox.last_start_result or {}
    base_url = start.get("internal_url", "http://localhost:3000")

    print(f"\n--- run_test_flow (base_url={base_url}) ---")
    print("First run may take ~1-2 min while Playwright/Firefox installs in E2B...")
    test_result = executor.execute(
        "run_test_flow",
        {
            "base_url": base_url,
            "steps": [
                {"action": "navigate", "path": "/"},
                {"action": "assert_visible", "selector": "h1"},
                {"action": "assert_text", "selector": "h1", "expected": "CodePilot Test"},
                {"action": "click", "selector": "#verifyBtn"},
                {"action": "assert_text", "selector": "#status", "expected": "Success!"},
            ],
            "timeout": 180,
        },
    )
    print(f"success={test_result.get('success')}")
    print(f"steps passed={sum(1 for s in test_result.get('steps', []) if s.get('passed'))}/{len(test_result.get('steps', []))}")
    if test_result.get("error"):
        print(f"error={test_result['error']}")
    if test_result.get("runner_stdout"):
        print(f"runner_stdout={test_result['runner_stdout'][:500]}")
    if test_result.get("runner_stderr"):
        print(f"runner_stderr={test_result['runner_stderr'][:500]}")

    print("\n--- generate_verification_report ---")
    report = executor.execute(
        "generate_verification_report",
        {"summary": "Browser verification E2B test"},
    )
    print(f"report success={report.get('success')}, overall={report.get('overall_result')}")
    if report.get("report_path"):
        print(f"report_path={report['report_path']}")

    print("\n--- destroy_sandbox ---")
    executor.execute("destroy_sandbox", {})

    if test_result.get("success") and report.get("success"):
        print("\nBROWSER VERIFICATION TEST: PASSED")
        return 0

    print("\nBROWSER VERIFICATION TEST: FAILED")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
