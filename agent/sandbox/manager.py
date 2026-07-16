"""
Sandbox manager.

Owns the full lifecycle of a single Docker container that acts as the
isolated execution environment for one agent task:

  create()            -> start a fresh, resource-limited container
  exec_command()       -> run a one-off command inside it (with timeout)
  start_application()  -> launch a long-running process (e.g. a dev server)
  run_test_flow()       -> drive Playwright through an ordered user flow
  generate_report()      -> compile everything into a verification report
  stop_application()   -> kill the running app process
  destroy()             -> remove the container entirely

MVP scope: one sandbox per task/session. If you need concurrent sandboxes
later (multiple sessions in parallel), promote this into a SandboxPool
keyed by session_id rather than adding that complexity here.

The project directory (Workspace.root) is bind-mounted into the container
at /workspace, so file edits made on the host via create_file/read_file
are immediately visible inside the container, and vice versa — no need
to copy files in and out.
"""

import json
import os
import shlex
import threading
import time

import docker
from docker.errors import APIError, DockerException, ImageNotFound


class SandboxError(Exception):
    """Raised for sandbox-related failures that tool handlers should
    turn into a clean {"success": False, "error": ...} result."""


class SandboxManager:
    def __init__(self, workspace_root: str, config):
        self.workspace_root = workspace_root
        self.config = config

        # Deliberately NOT connecting to Docker here. If the daemon isn't
        # running, we want that to surface as a clean {"success": False}
        # tool result when create_sandbox is called — not a raw traceback
        # at app startup, before the agent has even begun.
        self._client = None
        self.container = None
        self.container_port = 3000
        self.host_port = None
        self.created_at = None

        # State kept purely so generate_report() can compile a full
        # picture without the agent having to re-supply everything it
        # already told us via start_application/run_test_flow.
        self.last_start_result = None
        self.last_test_result = None

        self._destroyed_event = threading.Event()
        self._destroyed_event.set()  # starts "destroyed" until create() runs
        self._watchdog_thread = None

    @property
    def is_active(self) -> bool:
        return self.container is not None and not self._destroyed_event.is_set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def create(self) -> dict:
        if self.is_active:
            return {"success": False, "error": "A sandbox is already active. Destroy it first."}

        try:
            if self._client is None:
                self._client = docker.from_env()
        except DockerException as e:
            self._client = None
            return {
                "success": False,
                "error": f"Could not connect to Docker: {e}. Is Docker running?",
            }

        try:
            self.container = self._client.containers.run(
                self.config.docker_image,
                command="sleep infinity",
                detach=True,
                working_dir="/workspace",
                volumes={self.workspace_root: {"bind": "/workspace", "mode": "rw"}},
                # Publish the app port to a host port Docker picks automatically,
                # so start_application can read back whatever it was assigned.
                ports={f"{self.container_port}/tcp": None},
                # --- Resource limits ---
                mem_limit=self.config.sandbox_mem_limit,
                nano_cpus=self.config.sandbox_nano_cpus,
                pids_limit=self.config.sandbox_pids_limit,
                # --- Restricted permissions ---
                cap_drop=["ALL"],
                security_opt=["no-new-privileges"],
                # Outbound network is left enabled (bridge mode) so
                # install_dependencies can reach npm/pip registries.
                # See README "Safety" for tightening this further
                # (egress allowlisting, no-network mode, etc).
                network_mode="bridge",
                auto_remove=False,
            )
        except ImageNotFound:
            self.container = None
            return {
                "success": False,
                "error": (
                    f"Docker image '{self.config.docker_image}' was not found locally. "
                    "This is a custom image — unlike public images (e.g. 'alpine'), it is "
                    "never auto-pulled from a registry, so it must be built once before "
                    f"first use. Fix: docker build -t {self.config.docker_image} ./sandbox"
                ),
            }
        except DockerException as e:
            self.container = None
            return {"success": False, "error": f"Failed to create sandbox: {e}"}

        self.created_at = time.time()
        self.last_start_result = None
        self.last_test_result = None
        self._destroyed_event.clear()
        self._start_watchdog()

        return {"success": True, "sandbox_id": self.container.id[:12], "status": "running"}

    def _start_watchdog(self):
        """
        Safety net: force-destroy the container if it outlives its TTL,
        regardless of whether the agent ever calls destroy_sandbox. Protects
        against runaway loops or crashed sessions leaking containers.
        """
        ttl = self.config.sandbox_ttl_s

        def _watch():
            # Blocks until either the TTL elapses or destroy() sets the event.
            triggered = self._destroyed_event.wait(timeout=ttl)
            if not triggered and self.is_active:
                self.destroy()

        self._watchdog_thread = threading.Thread(target=_watch, daemon=True)
        self._watchdog_thread.start()

    def destroy(self) -> dict:
        if not self.is_active:
            self._destroyed_event.set()
            return {"success": True, "note": "No active sandbox to destroy."}

        try:
            self.container.remove(force=True)
        except DockerException as e:
            return {"success": False, "error": f"Failed to destroy sandbox: {e}"}
        finally:
            self.container = None
            self.host_port = None
            self._destroyed_event.set()

        return {"success": True, "status": "destroyed"}

    # ------------------------------------------------------------------
    # Command execution
    # ------------------------------------------------------------------

    def _require_active(self):
        if not self.is_active:
            raise SandboxError("No active sandbox. Call create_sandbox first.")

    def exec_command(self, command: str, timeout: int = 30) -> dict:
        """Run a one-off command inside the sandbox, enforcing a hard
        wall-clock timeout via the container's own `timeout` utility."""
        self._require_active()

        wrapped = f"timeout {int(timeout)} sh -c {shlex.quote(command)}"

        try:
            exit_code, output = self.container.exec_run(
                wrapped, workdir="/workspace", demux=True
            )
        except APIError as e:
            return {"success": False, "error": f"Docker exec failed: {e}"}

        stdout_b, stderr_b = output if output else (b"", b"")
        stdout = (stdout_b or b"").decode("utf-8", errors="replace")[-4000:]
        stderr = (stderr_b or b"").decode("utf-8", errors="replace")[-4000:]

        if exit_code == 124:  # `timeout` reserves 124 for "process timed out"
            return {
                "success": False,
                "exit_code": exit_code,
                "error": f"Command timed out after {timeout}s",
                "stdout": stdout,
                "stderr": stderr,
            }

        return {"success": exit_code == 0, "exit_code": exit_code, "stdout": stdout, "stderr": stderr}

    # ------------------------------------------------------------------
    # Long-running application process
    # ------------------------------------------------------------------

    def start_application(self, command: str, port: int | None = None) -> dict:
        """
        Launch a long-running process (e.g. a dev server) in the background
        inside the container. Its stdout/stderr are redirected to
        .sandbox/app.log INSIDE THE WORKSPACE, so the agent can read errors
        back out via the ordinary read_file tool — no new tool needed just
        to observe logs.
        """
        self._require_active()
        port = port or self.container_port

        log_dir = "/workspace/.sandbox"
        launch = (
            f"mkdir -p {log_dir} && "
            f"sh -c {shlex.quote(command)} > {log_dir}/app.log 2>&1 & "
            f"echo $! > {log_dir}/app.pid"
        )

        try:
            self.container.exec_run(f'sh -c "{launch}"', workdir="/workspace")
        except APIError as e:
            result = {"success": False, "error": f"Failed to start application: {e}"}
            self.last_start_result = result
            return result

        time.sleep(1.5)  # brief grace period for the process to bind its port

        self.container.reload()
        port_bindings = self.container.attrs["NetworkSettings"]["Ports"].get(f"{port}/tcp")
        if not port_bindings:
            result = {
                "success": False,
                "error": (
                    f"Container port {port} has no host mapping. Either the "
                    "process failed to start (check .sandbox/app.log via "
                    "read_file) or it's listening on a different port."
                ),
            }
            self.last_start_result = result
            return result

        self.host_port = port_bindings[0]["HostPort"]
        result = {
            "success": True,
            "command": command,
            "port": port,
            "exposed_url": f"http://localhost:{self.host_port}",
            "internal_url": f"http://localhost:{port}",
            "note": (
                "Use 'internal_url' when calling run_test_flow (Playwright runs "
                "inside this same container). Use 'exposed_url' if a human needs "
                "to open it in a browser on the host. "
                "Read '.sandbox/app.log' with read_file to check startup output/errors."
            ),
        }
        self.last_start_result = result
        return result

    def stop_application(self) -> dict:
        self._require_active()

        check_cmd = 'test -f /workspace/.sandbox/app.pid && cat /workspace/.sandbox/app.pid || true'
        try:
            _, output = self.container.exec_run(f'sh -c "{check_cmd}"', workdir="/workspace")
        except APIError as e:
            return {"success": False, "error": f"Failed to check running process: {e}"}

        pid = (output or b"").decode().strip()
        if not pid:
            return {"success": True, "note": "No running application process found (already stopped?)."}

        self.container.exec_run(f'sh -c "kill -9 {pid} 2>/dev/null || true"')
        return {"success": True, "note": f"Stopped process with pid {pid}."}

    # ------------------------------------------------------------------
    # Verification (Playwright test flow)
    # ------------------------------------------------------------------

    def run_test_flow(self, base_url: str, steps: list, record_video: bool = False, timeout: int = 90) -> dict:
        """
        Drive the baked-in Playwright runner through an ordered sequence
        of user-flow steps (navigate/click/fill/assert) against `base_url`
        inside the container.

        The spec is written directly to the host-side workspace directory
        (which is bind-mounted into the container), rather than piped
        through docker exec's stdin — simpler, and avoids interleaving
        with the browser's own stdout noise. The result is read back the
        same way, from a JSON file the runner always writes, even on
        internal failure.

        The result is cached on self.last_test_result so generate_report()
        can compile it without the agent needing to repeat it.
        """
        self._require_active()

        sandbox_dir_host = os.path.join(self.workspace_root, ".sandbox")
        os.makedirs(sandbox_dir_host, exist_ok=True)

        spec_path_host = os.path.join(sandbox_dir_host, "test_spec.json")
        result_path_host = os.path.join(sandbox_dir_host, "test_result.json")

        # Clear any stale result from a previous run so a crash here can
        # never be mistaken for a leftover pass from an earlier attempt.
        if os.path.exists(result_path_host):
            os.remove(result_path_host)

        with open(spec_path_host, "w") as f:
            json.dump({"base_url": base_url, "steps": steps, "record_video": record_video}, f)

        runner = "/opt/agent-tools/venv/bin/python3 /opt/agent-tools/run_test_flow.py"
        command = f"{runner} /workspace/.sandbox/test_spec.json /workspace/.sandbox/test_result.json"

        exec_result = self.exec_command(command, timeout=timeout)

        if not os.path.exists(result_path_host):
            test_result = {
                "success": False,
                "steps": [],
                "screenshots": [],
                "video": None,
                "error": "Test runner did not produce a result file — it likely crashed or timed out.",
                "runner_stdout": exec_result.get("stdout", ""),
                "runner_stderr": exec_result.get("stderr", ""),
            }
        else:
            with open(result_path_host, "r") as f:
                test_result = json.load(f)

        self.last_test_result = test_result
        return test_result

    # ------------------------------------------------------------------
    # Verification report
    # ------------------------------------------------------------------

    def _suggest_next_action(self, overall_result: str, test_result: dict | None) -> str:
        """
        Rule-based, not AI-inferred — a plain lookup from the verdict to a
        concrete next step, so an external agent (or a human) knows what
        this platform expects to happen next. Deliberately simple: this
        is meant to be a reliable, predictable signal, not a "smart"
        recommendation that could vary between runs of the same result.
        """
        if overall_result == "PASS":
            return "No action needed. Verification passed — safe to return this work to the developer."
        if self.last_start_result and not self.last_start_result.get("success"):
            return "The application failed to start. Fix the start command or missing dependencies, then resubmit for verification."
        if test_result and test_result.get("error"):
            return "The test runner itself failed to complete (not a test failure). Check the error detail, fix the underlying issue, then resubmit."
        if overall_result == "FAIL":
            return "One or more tests failed. Review the failed steps and errors below, apply a fix, and resubmit for verification."
        return "No test flow was executed. Resubmit with a defined test flow to get a pass/fail verdict before returning this work to the developer."

    def _build_machine_readable_result(self, summary: str, overall_result: str, test_result: dict | None, generated_at: str) -> dict:
        """
        The agent-to-agent counterpart to the Markdown report generated
        alongside it in generate_report() — same underlying data
        (self.last_start_result, self.last_test_result), restructured as
        a stable, parseable object instead of prose. Adding fields here
        is safe and backward compatible; existing consumers of
        generate_report()'s Markdown "content" field are unaffected.
        """
        steps = (test_result or {}).get("steps", []) or []
        tests_passed = sum(1 for s in steps if s.get("passed"))
        tests_failed = sum(1 for s in steps if not s.get("passed"))

        errors = []
        if self.last_start_result and not self.last_start_result.get("success"):
            errors.append({"source": "application_start", "detail": self.last_start_result.get("error")})
        if test_result and test_result.get("error"):
            errors.append({"source": "test_runner", "detail": test_result["error"]})
        for s in steps:
            if not s.get("passed"):
                errors.append({"source": "test_step", "step_index": s.get("index"), "detail": s.get("detail")})
        for console_error in (test_result or {}).get("console_errors", []) or []:
            errors.append({"source": "console", "detail": console_error})

        return {
            "schema_version": "1.0",
            "status": overall_result,
            "summary": summary,
            "tests": {"passed": tests_passed, "failed": tests_failed, "total": len(steps)},
            "errors": errors,
            "evidence": {
                "screenshots": (test_result or {}).get("screenshots", []) or [],
                "video": (test_result or {}).get("video"),
                "logs": (test_result or {}).get("console_errors", []) or [],
            },
            "application": {
                "started": bool(self.last_start_result and self.last_start_result.get("success")),
                "internal_url": (self.last_start_result or {}).get("internal_url"),
                "exposed_url": (self.last_start_result or {}).get("exposed_url"),
            },
            "repair_attempts_used": (test_result or {}).get("repair_attempts_used", 0),
            "execution_time_seconds": round(time.time() - self.created_at, 2) if self.created_at else None,
            "suggested_next_action": self._suggest_next_action(overall_result, test_result),
            "human_readable_report_path": ".sandbox/verification_report.md",
            "generated_at": generated_at,
        }

    def generate_report(self, summary: str) -> dict:
        """
        Compile everything we know about this session — application
        status, the most recent test flow results, evidence paths, and an
        overall verdict — into a single Markdown report written to
        .sandbox/verification_report.md in the project workspace.

        Deliberately pulls from cached state (self.last_start_result,
        self.last_test_result) rather than requiring the agent to repeat
        details it already provided via earlier tool calls.
        """
        sandbox_dir_host = os.path.join(self.workspace_root, ".sandbox")
        os.makedirs(sandbox_dir_host, exist_ok=True)
        report_path_host = os.path.join(sandbox_dir_host, "verification_report.md")

        timestamp = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
        lines = ["# Verification Report", "", f"**Generated:** {timestamp}", "", f"**Summary:** {summary}", ""]

        # --- Quick verdict (compact format) ---
        simple_report = (self.last_test_result or {}).get("simple_report")
        if simple_report:
            lines.append("## Quick Verdict")
            lines.append("```")
            lines.append(simple_report["text"])
            lines.append("```")
            lines.append("")

        # --- Application status ---
        lines.append("## Application Status")
        if self.last_start_result and self.last_start_result.get("success"):
            lines.append(f"- Started successfully with command: `{self.last_start_result.get('command')}`")
            lines.append(f"- Internal URL (used for testing): `{self.last_start_result.get('internal_url')}`")
            lines.append(f"- Exposed URL (for a human to view): `{self.last_start_result.get('exposed_url')}`")
        elif self.last_start_result:
            lines.append(f"- **Failed to start.** Error: {self.last_start_result.get('error')}")
        else:
            lines.append("- The application was never started via start_application.")
        lines.append("")

        # --- Test flow results ---
        lines.append("## Test Flow Results")
        test_result = self.last_test_result
        if test_result is None:
            lines.append("- No test flow was executed via run_test_flow.")
            overall_result = "NOT TESTED"
        elif test_result.get("error"):
            lines.append(f"- **Test runner failed to complete.** {test_result['error']}")
            overall_result = "FAIL"
        else:
            steps = test_result.get("steps", [])
            passed_count = sum(1 for s in steps if s.get("passed"))
            lines.append(f"**{passed_count}/{len(steps)} steps passed**")
            lines.append("")
            lines.append("| # | Action | Selector | Expected | Result | Detail |")
            lines.append("|---|---|---|---|---|---|")
            for s in steps:
                status = "PASS" if s.get("passed") else "FAIL"
                lines.append(
                    f"| {s.get('index')} | {s.get('action')} | {s.get('selector') or ''} | "
                    f"{s.get('expected') if s.get('expected') is not None else ''} | {status} | {s.get('detail', '')} |"
                )
            lines.append("")

            console_count = test_result.get("console_error_count", 0)
            if console_count:
                lines.append(f"**Console errors detected:** {console_count}")
                for msg in test_result.get("console_errors", []):
                    lines.append(f"- {msg}")
                lines.append("")

            if test_result.get("screenshots"):
                lines.append("**Screenshots:**")
                for s in test_result["screenshots"]:
                    lines.append(f"- `{s}`")
                lines.append("")

            if test_result.get("video"):
                lines.append(f"**Session recording:** `{test_result['video']}`")
                lines.append("")

            overall_result = "PASS" if test_result.get("success") else "FAIL"

        # --- Debugging agent repair attempts ---
        repair_attempts = (test_result or {}).get("repair_attempts") if test_result else None
        if repair_attempts:
            lines.append("## Debugging Agent Repair Attempts")
            lines.append(
                f"**{test_result.get('repair_attempts_used', len(repair_attempts))} repair attempt(s) made "
                f"(max {len(repair_attempts)} shown).**"
            )
            lines.append("")
            for entry in repair_attempts:
                lines.append(f"**Attempt {entry.get('attempt')}:**")
                if entry.get("success"):
                    lines.append(f"- {entry.get('explanation', '(no explanation given)')}")
                else:
                    lines.append(f"- Did not conclude a fix: {entry.get('explanation', '')}")
                files_touched = sorted(
                    {
                        a["input"].get("path")
                        for a in entry.get("actions", [])
                        if a.get("tool") == "create_file" and a.get("input", {}).get("path")
                    }
                )
                if files_touched:
                    lines.append(f"- Files modified: {', '.join(files_touched)}")
                lines.append("")

        # --- Final result ---
        lines.append("## Final Result")
        lines.append(f"**{overall_result}**")
        lines.append("")

        content = "\n".join(lines)
        with open(report_path_host, "w", encoding="utf-8") as f:
            f.write(content)

        return {
            "success": True,
            "report_path": ".sandbox/verification_report.md",
            "overall_result": overall_result,
            "content": content,
            "machine_readable": self._build_machine_readable_result(summary, overall_result, test_result, timestamp),
        }
        