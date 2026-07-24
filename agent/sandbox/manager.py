"""
Sandbox manager.

Owns the full lifecycle of a single E2B sandbox that acts as the
isolated execution environment for one agent task:

  create()            -> start a fresh cloud sandbox
  exec_command()       -> run a one-off command inside it (with timeout)
  start_application()  -> launch a long-running process (e.g. a dev server)
  run_test_flow()       -> drive Playwright through an ordered user flow
  generate_report()      -> compile everything into a verification report
  stop_application()   -> kill the running app process
  destroy()             -> remove the sandbox entirely

MVP scope: one sandbox per task/session. If you need concurrent sandboxes
later (multiple sessions in parallel), promote this into a SandboxPool
keyed by session_id rather than adding that complexity here.
"""

import json
import os
import threading
import time

from e2b import Sandbox


class SandboxError(Exception):
    """Raised for sandbox-related failures that tool handlers should
    turn into a clean {"success": False, "error": ...} result."""


class SandboxManager:
    def __init__(self, workspace_root: str, config):
        self.workspace_root = workspace_root
        self.config = config

        # Deliberately NOT connecting to E2B here. If the API key isn't
        # configured or valid, we want that to surface as a clean {"success": False}
        # tool result when create_sandbox is called — not a raw traceback
        # at app startup, before the agent has even begun.
        self.sandbox = None
        self.container_port = 3000
        self.host_port = None
        self.created_at = None
        self._app_process = None
        self._workdir = None

        # State kept purely so generate_report() can compile a full
        # picture without the agent having to re-supply everything it
        # already told us via start_application/run_test_flow.
        self.last_start_result = None
        self.last_test_result = None

        self._destroyed_event = threading.Event()
        self._destroyed_event.set()  # starts "destroyed" until create() runs
        self._watchdog_thread = None
        self._playwright_ready = False
        self._runner_scripts_bundled = False

    @property
    def is_active(self) -> bool:
        return self.sandbox is not None and not self._destroyed_event.is_set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def create(self) -> dict:
        if self.is_active:
            return {
                "success": False,
                "error": "A sandbox is already active."
            }

        try:
            self.sandbox = Sandbox.create()
            self._destroyed_event.clear()
            self._workdir = None
            workdir = self.get_working_directory()
            self.sandbox.commands.run(f"mkdir -p {workdir}/.sandbox")

        except Exception as e:
            if self.sandbox:
                try:
                    self.sandbox.kill()
                except Exception:
                    pass
                self.sandbox = None
            self._destroyed_event.set()
            return {
                "success": False,
                "error": f"E2B sandbox creation failed: {e}"
            }

        self.created_at = time.time()
        self.last_start_result = None
        self.last_test_result = None
        self._app_process = None

        self._start_watchdog()

        return {
            "success": True,
            "sandbox_id": self.sandbox.sandbox_id,
            "status": "running"
        }

    def _start_watchdog(self):
        """
        Safety net: force-destroy the sandbox if it outlives its TTL,
        regardless of whether the agent ever calls destroy_sandbox. Protects
        against runaway loops or crashed sessions leaking sandboxes.
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
            return {
                "success": True,
                "note": "No active sandbox to destroy."
            }

        try:
            self.sandbox.kill()

        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to destroy sandbox: {e}"
            }

        finally:
            self.sandbox = None
            self._app_process = None
            self._workdir = None
            self._destroyed_event.set()

        return {
            "success": True,
            "status": "destroyed"
        }

    # ------------------------------------------------------------------
    # Command execution
    # ------------------------------------------------------------------

    def get_working_directory(self) -> str:
        if self._workdir:
            return self._workdir
        if not self.is_active:
            raise SandboxError("No active sandbox. Call create_sandbox first.")
        try:
            res = self.sandbox.commands.run("pwd")
            self._workdir = (res.stdout or "").strip() or "/home/user"
            return self._workdir
        except Exception:
            self._workdir = "/home/user"
            return self._workdir

    def sync_workspace(self) -> dict:
        """
        Sync all files from the host workspace (self.workspace_root) directly
        into the E2B sandbox's working directory before executing commands or
        starting applications.
        """
        self._require_active()
        workdir = self.get_working_directory()

        if not self.workspace_root or not os.path.exists(self.workspace_root):
            return {"success": True, "synced_files": 0}

        ignore_dirs = {".sandbox", ".git", "__pycache__", "venv", "node_modules", ".pytest_cache", ".mypy_cache"}
        synced_count = 0

        for root, dirs, files in os.walk(self.workspace_root):
            dirs[:] = [d for d in dirs if d not in ignore_dirs and not d.startswith("._")]
            for filename in files:
                if filename.startswith("._") or filename.endswith(".pyc"):
                    continue
                local_path = os.path.join(root, filename)
                rel_path = os.path.relpath(local_path, self.workspace_root).replace("\\", "/")
                remote_path = f"{workdir}/{rel_path}" if rel_path != "." else workdir
                try:
                    with open(local_path, "rb") as f:
                        content = f.read()
                    self.sandbox.files.write(remote_path, content)
                    synced_count += 1
                except Exception:
                    pass

        return {"success": True, "synced_files": synced_count}

    def _repo_scripts_dir(self) -> str:
        """Path to sandbox/scripts in the CodePilot repo (on the host)."""
        return os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "sandbox", "scripts")
        )

    def _bundle_test_runner_scripts(self) -> dict:
        """
        Upload the Playwright test runner scripts into the E2B workspace.

        Web session workspaces only contain agent-created project files.
        Without this step, run_test_flow looks for {workdir}/sandbox/scripts/
        which does not exist on a default E2B template.
        """
        if self._runner_scripts_bundled:
            return {"success": True, "uploaded_files": 0, "note": "already bundled"}

        self._require_active()
        scripts_dir = self._repo_scripts_dir()
        if not os.path.isdir(scripts_dir):
            return {
                "success": False,
                "error": f"Test runner scripts not found at {scripts_dir}",
            }

        workdir = self.get_working_directory()
        uploaded = 0
        for root, dirs, files in os.walk(scripts_dir):
            dirs[:] = [d for d in dirs if d not in ("__pycache__", ".pytest_cache")]
            for filename in files:
                if filename.endswith((".pyc", ".pyo")):
                    continue
                local_path = os.path.join(root, filename)
                rel = os.path.relpath(local_path, scripts_dir).replace("\\", "/")
                remote_path = f"{workdir}/sandbox/scripts/{rel}"
                with open(local_path, "rb") as f:
                    content = f.read()
                self.sandbox.files.write(remote_path, content)
                uploaded += 1

        self._runner_scripts_bundled = True
        return {"success": True, "uploaded_files": uploaded}

    def _ensure_playwright(self) -> dict:
        """Install Playwright + Chromium inside the E2B sandbox if needed."""
        if self._playwright_ready:
            return {"success": True}

        self._require_active()
        workdir = self.get_working_directory()

        try:
            check = self.sandbox.commands.run(
                "python3 -c \"import playwright; print('ok')\" 2>/dev/null || echo missing",
                cwd=workdir,
                timeout=30,
            )
        except Exception as e:
            return {"success": False, "error": f"Playwright check failed: {e}"}

        if (check.stdout or "").strip() != "ok":
            try:
                pip = self.sandbox.commands.run(
                    "python3 -m pip install -q playwright",
                    cwd=workdir,
                    timeout=120,
                )
            except Exception as e:
                return {"success": False, "error": f"pip install playwright failed: {e}"}
            if pip.exit_code != 0:
                return {
                    "success": False,
                    "error": f"pip install playwright failed: {pip.stderr or pip.stdout}",
                }

        try:
            install = self.sandbox.commands.run(
                "python3 -m playwright install chromium 2>&1",
                cwd=workdir,
                timeout=300,
            )
        except Exception as e:
            return {"success": False, "error": f"playwright install chromium failed: {e}"}

        if install.exit_code != 0:
            return {
                "success": False,
                "error": (
                    "playwright install chromium failed: "
                    f"{install.stderr or install.stdout}"
                ),
            }

        self._playwright_ready = True
        return {"success": True}

    def sync_from_sandbox(self, paths: list[str] | None = None) -> None:
        """Download specified paths from E2B .sandbox/ back to host workspace if they exist."""
        if not self.is_active or not self.workspace_root:
            return
        try:
            workdir = self.get_working_directory()
        except Exception:
            return
        paths = paths or [".sandbox/app.log", ".sandbox/app.pid", ".sandbox/test_result.json", ".sandbox/test_spec.json"]
        for rel_path in paths:
            clean_rel = rel_path.lstrip("/")
            remote_path = f"{workdir}/{clean_rel}"
            local_path = os.path.join(self.workspace_root, clean_rel)
            try:
                content = self.sandbox.files.read(remote_path)
                if content is not None:
                    if isinstance(content, bytes):
                        content_str = content.decode("utf-8", errors="replace")
                    else:
                        content_str = content
                    os.makedirs(os.path.dirname(local_path), exist_ok=True)
                    with open(local_path, "w", encoding="utf-8") as f:
                        f.write(content_str)
            except Exception:
                pass

    def read_sandbox_file(self, path: str) -> str | None:
        """Read a file directly from the E2B sandbox without needing host bind-mounts."""
        if not self.is_active:
            return None
        try:
            workdir = self.get_working_directory()
            clean_rel = path.lstrip("/")
            remote_path = f"{workdir}/{clean_rel}"
            content = self.sandbox.files.read(remote_path)
            if content is not None:
                if isinstance(content, bytes):
                    return content.decode("utf-8", errors="replace")
                return content
        except Exception:
            pass
        return None

    def _require_active(self):
        if not self.is_active:
            raise SandboxError("No active sandbox. Call create_sandbox first.")
        workdir = self.get_working_directory()
        try:
            self.sandbox.commands.run(f"mkdir -p {workdir}/.sandbox")
        except Exception as e:
            raise SandboxError(f"Failed to ensure .sandbox directory in sandbox working directory ({workdir}): {e}")

    def exec_command(self, command: str, timeout: int = 30) -> dict:
        """Run a one-off command inside the sandbox, enforcing a hard
        wall-clock timeout using E2B's native timeout parameter."""
        self._require_active()
        self.sync_workspace()
        workdir = self.get_working_directory()

        try:
            result = self.sandbox.commands.run(
                command, cwd=workdir, timeout=timeout
            )
        except Exception as e:
            if "timeout" in str(e).lower() or type(e).__name__ == "TimeoutException" or isinstance(e, TimeoutError):
                return {
                    "success": False,
                    "exit_code": 124,
                    "error": f"Command timed out after {timeout}s",
                    "stdout": "",
                    "stderr": str(e),
                }
            return {"success": False, "error": f"E2B exec failed: {e}"}

        exit_code = result.exit_code if result.exit_code is not None else 0
        stdout = result.stdout or ""
        stderr = result.stderr or ""

        self.sync_from_sandbox()
        return {"success": exit_code == 0, "exit_code": exit_code, "stdout": stdout, "stderr": stderr}

    # ------------------------------------------------------------------
    # Long-running application process
    # ------------------------------------------------------------------

    def start_application(self, command: str, port: int | None = None) -> dict:
        """
        Launch a long-running process (e.g. a dev server) in the background
        inside the sandbox. Its stdout/stderr are redirected to
        .sandbox/app.log INSIDE THE WORKSPACE, so the agent can read errors
        back out via the ordinary read_file tool — no new tool needed just
        to observe logs.
        """
        self._require_active()
        self.sync_workspace()
        workdir = self.get_working_directory()
        port = port or self.container_port

        log_dir = f"{workdir}/.sandbox"
        launch_cmd = (
            f"mkdir -p {log_dir} && "
            f"({command}) > {log_dir}/app.log 2>&1 & "
            f"echo $! > {log_dir}/app.pid && "
            f"wait $!"
        )

        try:
            self._app_process = self.sandbox.commands.run(
                launch_cmd, background=True, cwd=workdir, timeout=0
            )
        except Exception as e:
            result = {"success": False, "error": f"Failed to start application: {e}"}
            self.last_start_result = result
            return result

        time.sleep(1.5)  # brief grace period for the process to bind its port

        try:
            exposed_url = self.sandbox.get_host(port)
        except Exception as e:
            result = {
                "success": False,
                "error": f"Failed to get exposed host URL for port {port}: {e}",
            }
            self.last_start_result = result
            return result

        if not exposed_url:
            result = {
                "success": False,
                "error": (
                    f"Sandbox port {port} could not be exposed. Either the "
                    "process failed to start (check .sandbox/app.log via "
                    "read_file) or it's listening on a different port."
                ),
            }
            self.last_start_result = result
            return result

        if not exposed_url.startswith("http://") and not exposed_url.startswith("https://"):
            exposed_url = f"https://{exposed_url}"

        result = {
            "success": True,
            "command": command,
            "port": port,
            "exposed_url": exposed_url,
            "internal_url": f"http://localhost:{port}",
            "note": (
                "Use 'internal_url' when calling run_test_flow (Playwright runs "
                "inside this same sandbox). Use 'exposed_url' if a human needs "
                "to open it in a browser on the host. "
                "Read '.sandbox/app.log' with read_file to check startup output/errors."
            ),
        }
        self.last_start_result = result
        self.sync_from_sandbox()
        return result

    def stop_application(self) -> dict:
        self._require_active()
        workdir = self.get_working_directory()

        stopped_via_handle = False
        if self._app_process is not None:
            try:
                self._app_process.kill()
                stopped_via_handle = True
            except Exception:
                pass
            finally:
                self._app_process = None

        # Fallback / cleanup: PID-based kill via commands.run
        check_cmd = f"test -f {workdir}/.sandbox/app.pid && cat {workdir}/.sandbox/app.pid || true"
        try:
            result = self.sandbox.commands.run(check_cmd, cwd=workdir)
            pid = (result.stdout or "").strip()
            if pid:
                self.sandbox.commands.run(f"kill -9 {pid} 2>/dev/null || true", cwd=workdir)
                self.sandbox.commands.run(f"rm -f {workdir}/.sandbox/app.pid", cwd=workdir)
                self.sync_from_sandbox()
                return {"success": True, "note": f"Stopped process with pid {pid}."}
        except Exception as e:
            if not stopped_via_handle:
                return {"success": False, "error": f"Failed to check/kill running process: {e}"}

        self.sync_from_sandbox()
        if stopped_via_handle:
            return {"success": True, "note": "Stopped application process via E2B CommandHandle."}

        return {"success": True, "note": "No running application process found (already stopped?)."}

    # ------------------------------------------------------------------
    # Verification (Playwright test flow)
    # ------------------------------------------------------------------

    def run_test_flow(self, base_url: str, steps: list, record_video: bool = False, timeout: int = 90) -> dict:
        """
        Drive the baked-in Playwright runner through an ordered sequence
        of user-flow steps (navigate/click/fill/assert) against `base_url`
        inside the sandbox.

        The spec and result files are written/read using E2B's filesystem API
        (self.sandbox.files.write / read), since there is no host bind-mount
        in E2B cloud sandboxes.

        The result is cached on self.last_test_result so generate_report()
        can compile it without the agent needing to repeat it.
        """
        self._require_active()
        self.sync_workspace()
        workdir = self.get_working_directory()

        # Clear any stale result from a previous run inside the sandbox so a crash
        # here can never be mistaken for a leftover pass from an earlier attempt.
        self.exec_command(f"mkdir -p {workdir}/.sandbox && rm -f {workdir}/.sandbox/test_result.json")

        spec_content = json.dumps({"base_url": base_url, "steps": steps, "record_video": record_video})
        self.sandbox.files.write(f"{workdir}/.sandbox/test_spec.json", spec_content)

        check_cmd = "test -f /opt/agent-tools/run_test_flow.py && echo opt || echo local"
        try:
            res = self.sandbox.commands.run(check_cmd, cwd=workdir)
            is_opt = (res.stdout or "").strip() == "opt"
        except Exception:
            is_opt = False

        if is_opt:
            runner = "/opt/agent-tools/venv/bin/python3 /opt/agent-tools/run_test_flow.py"
            command = f"WORKSPACE_ROOT={workdir} {runner} {workdir}/.sandbox/test_spec.json {workdir}/.sandbox/test_result.json"
        else:
            bundle = self._bundle_test_runner_scripts()
            if not bundle.get("success"):
                return {
                    "success": False,
                    "steps": [],
                    "screenshots": [],
                    "video": None,
                    "error": bundle.get("error", "Failed to bundle test runner scripts"),
                }

            pw = self._ensure_playwright()
            if not pw.get("success"):
                return {
                    "success": False,
                    "steps": [],
                    "screenshots": [],
                    "video": None,
                    "error": pw.get("error", "Failed to install Playwright"),
                }

            runner = f"python3 {workdir}/sandbox/scripts/run_test_flow.py"
            command = f"PYTHONPATH={workdir}:{workdir}/sandbox/scripts:$PYTHONPATH WORKSPACE_ROOT={workdir} {runner} {workdir}/.sandbox/test_spec.json {workdir}/.sandbox/test_result.json"

        # First Playwright run may include a long bootstrap; allow extra time.
        exec_timeout = max(timeout, 180)
        exec_result = self.exec_command(command, timeout=exec_timeout)
        self.sync_from_sandbox([".sandbox/app.log", ".sandbox/test_result.json", ".sandbox/test_spec.json"])

        try:
            raw_result = self.sandbox.files.read(f"{workdir}/.sandbox/test_result.json")
            if isinstance(raw_result, bytes):
                raw_result = raw_result.decode("utf-8", errors="replace")
            test_result = json.loads(raw_result)
        except Exception:
            test_result = {
                "success": False,
                "steps": [],
                "screenshots": [],
                "video": None,
                "error": "Test runner did not produce a result file — it likely crashed or timed out.",
                "runner_stdout": exec_result.get("stdout", ""),
                "runner_stderr": exec_result.get("stderr", ""),
            }

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