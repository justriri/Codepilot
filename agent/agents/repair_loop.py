"""
Test Repair Loop.

Bounded orchestration: when a test flow fails, invoke the DebuggingAgent
to analyze and fix the code, restart the running application if one
exists (so the fix actually takes effect — a code edit alone does
nothing to an already-running process), and re-test. Repeats up to a
hard cap (max_repair_attempts), enforced in plain Python — not left to
either LLM's judgment — so a stubborn bug can never cause an infinite
loop.

This sits between ToolExecutor and SandboxManager: from the calling
agent's perspective, run_test_flow's tool contract (input/output shape)
is completely unchanged. It just quietly does more work and comes back
more reliable, with extra "repair_attempts" / "repair_attempts_used"
fields appended to the result for transparency/reporting.
"""


class TestRepairLoop:
    def __init__(self, sandbox_manager, debugging_agent, max_repair_attempts: int = 3):
        self.sandbox = sandbox_manager
        self.debugging_agent = debugging_agent
        self.max_repair_attempts = max_repair_attempts

    def run(self, tool_input: dict) -> dict:
        base_url = tool_input["base_url"]
        steps = tool_input.get("steps", [])
        record_video = tool_input.get("record_video", False)
        timeout = tool_input.get("timeout", 90)

        result = self.sandbox.run_test_flow(base_url, steps, record_video, timeout)

        repair_log = []
        attempts_used = 0

        while not result.get("success") and attempts_used < self.max_repair_attempts:
            attempts_used += 1

            try:
                debug_outcome = self.debugging_agent.analyze_and_fix(result)
            except Exception as e:
                # A broken debugging call (e.g. an API error) shouldn't crash
                # the whole tool call — stop repairing and hand back the last
                # known, properly-structured test result instead.
                repair_log.append(
                    {
                        "attempt": attempts_used,
                        "success": False,
                        "explanation": f"Debugging agent call failed: {e}",
                        "actions": [],
                    }
                )
                break

            repair_log.append({"attempt": attempts_used, **debug_outcome})

            self._restart_application_if_running()

            result = self.sandbox.run_test_flow(base_url, steps, record_video, timeout)

        result["repair_attempts"] = repair_log
        result["repair_attempts_used"] = attempts_used
        return result

    def _restart_application_if_running(self):
        """
        Restart the app between repair attempts so a code fix is actually
        loaded before re-testing. Safe no-op if nothing was ever started
        successfully (e.g. a static-file check with no server process).
        """
        last_start = self.sandbox.last_start_result
        if not last_start or not last_start.get("success"):
            return

        self.sandbox.stop_application()
        self.sandbox.start_application(last_start["command"], last_start.get("port"))
