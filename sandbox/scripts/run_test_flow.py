"""
CLI entry point for running a test flow inside the E2B cloud sandbox.

Thin orchestration layer: reads the spec, wires together
BrowserController + TestingAgent + the report generator, and writes the
structured result JSON that SandboxManager reads back on the host side.

This is intentionally a thin script — all real logic lives in
browser_controller.py, testing_agent.py, and report.py (siblings in this
same directory, all baked into the sandbox image at /opt/agent-tools/).

Usage:
    python3 run_test_flow.py <spec_path> <result_path>

Spec JSON: unchanged from before —
{
  "base_url": "http://localhost:3000",
  "record_video": true,
  "steps": [ {"action": "navigate", "path": "/"}, ... ]
}

Result JSON: same shape as before, PLUS a new "simple_report" field:
{
  "success": bool,
  "steps": [...],
  "screenshots": [...],
  "video": "<relative path or null>",
  "console_error_count": int,
  "console_errors": [...],
  "simple_report": {"application", "status", "tests_passed", "tests_failed", "screenshots", "logs", "text"}
}
"""

import json
import os
import sys
import traceback

from browser_controller import BrowserController
from testing_agent import TestingAgent
import report as report_module


def run(spec_path: str, result_path: str) -> dict:
    with open(spec_path, "r") as f:
        spec = json.load(f)

    base_url = spec["base_url"]
    steps = spec.get("steps", [])
    record_video = bool(spec.get("record_video", False))

    workspace_root = os.environ.get("WORKSPACE_ROOT", os.getcwd())
    browser = BrowserController(
        workspace_root=workspace_root,
        evidence_subdir=".sandbox/evidence",
        record_video=record_video,
    )
    tester = TestingAgent(browser, base_url)

    try:
        step_results = tester.run(steps)
    finally:
        # Always close the browser (and finalize any video), even if a
        # step raised something TestingAgent's own try/except didn't catch.
        browser.close_browser()

    screenshots = [s["screenshot"] for s in step_results if s.get("screenshot")]
    console_errors = browser.get_console_errors()

    # Reference the app's own log file as evidence too, if it exists —
    # its content isn't read here, but the agent can read it separately
    # via read_file if a step fails.
    logs_evidence = list(console_errors[:5])
    if os.path.exists(os.path.join(workspace_root, ".sandbox/app.log")):
        logs_evidence.append(".sandbox/app.log")

    simple_report = report_module.generate_report(base_url, step_results, screenshots, logs_evidence)

    return {
        "success": tester.all_passed,
        "steps": step_results,
        "screenshots": screenshots,
        "video": browser.video_path,
        "console_error_count": len(console_errors),
        "console_errors": console_errors[:5],
        "simple_report": simple_report,
    }


def main():
    spec_path, result_path = sys.argv[1], sys.argv[2]

    try:
        result = run(spec_path, result_path)
    except Exception as e:
        # Even if the runner itself blows up, always leave a result file
        # behind — the caller should never be left guessing whether
        # verification even attempted to run.
        result = {
            "success": False,
            "steps": [],
            "screenshots": [],
            "video": None,
            "console_error_count": 0,
            "console_errors": [],
            "simple_report": None,
            "error": f"Test flow runner failed: {e}\n{traceback.format_exc()}",
        }
        with open(result_path, "w") as f:
            json.dump(result, f, indent=2)
        sys.exit(1)

    with open(result_path, "w") as f:
        json.dump(result, f, indent=2)


if __name__ == "__main__":
    main()
