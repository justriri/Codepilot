"""
Verification Report generator (compact format).

Produces the at-a-glance verification summary:

    Application: <url>
    Status: <PASS|FAIL|NOT TESTED>
    Tests Passed: <n>
    Tests Failed: <n>
    Evidence:
    - Screenshots: [...]
    - Logs: [...]

This is a plain, human-readable verdict a user can read in a few
seconds. It gets embedded (as a "simple_report" field) inside the
richer, per-step JSON result returned by run_test_flow, and
SandboxManager.generate_report() surfaces it at the top of the full
Markdown report.
"""


def generate_report(application_url: str, test_results: list, screenshots: list, logs: list) -> dict:
    passed = sum(1 for r in test_results if r.get("passed"))
    failed = sum(1 for r in test_results if not r.get("passed"))

    if not test_results:
        status = "NOT TESTED"
    else:
        status = "PASS" if failed == 0 else "FAIL"

    lines = [
        f"Application: {application_url}",
        f"Status: {status}",
        f"Tests Passed: {passed}",
        f"Tests Failed: {failed}",
        "Evidence:",
        f"- Screenshots: {', '.join(screenshots) if screenshots else 'none'}",
        f"- Logs: {', '.join(logs) if logs else 'none'}",
    ]
    text = "\n".join(lines)

    return {
        "application": application_url,
        "status": status,
        "tests_passed": passed,
        "tests_failed": failed,
        "screenshots": screenshots,
        "logs": logs,
        "text": text,
    }
