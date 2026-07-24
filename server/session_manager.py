"""
Session Manager.

Runs one agent session per web request in its own background thread,
with its own Workspace, SandboxManager (-> its own E2B cloud sandbox),
DebuggingAgent, and TestRepairLoop — fully isolated from any other
concurrent session, mirroring exactly what main.py builds for a single
CLI run. SandboxManager is explicitly one-sandbox-per-session (see its
own docstring), so reusing a single shared instance across concurrent
web requests would let two users collide on the same sandbox; this
avoids that by constructing the whole dependency graph fresh per
session, same as main.py does.

In-memory only for this MVP — sessions are lost on server restart, same
tradeoff already accepted throughout this project (no persistence layer
yet). Fine for a single local developer; not for multi-user production.
"""

import queue
import textwrap
import threading
import uuid
from dataclasses import dataclass, field
from typing import Optional

from agent.config import load_config
from agent.workspace import Workspace
from agent.sandbox.manager import SandboxManager
from agent.agents.debugging_agent import DebuggingAgent
from agent.agents.repair_loop import TestRepairLoop
from agent.tools.executor import ToolExecutor
from agent.controller import AgentController
from providers.router import get_provider

SESSIONS_ROOT = "./web_sessions"

_DEMO_HTML = textwrap.dedent("""
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


@dataclass
class Session:
    id: str
    request: str
    workspace_root: str
    status: str = "running"  # running | done | error
    events: list = field(default_factory=list)
    result: Optional[str] = None
    # Populated as soon as generate_verification_report's tool_result
    # arrives, from its "machine_readable" field — cached directly on the
    # session so an external agent (or the frontend) can retrieve just
    # the structured verdict without searching the full event list.
    verification_result: Optional[dict] = None
    subscribers: list = field(default_factory=list)  # list[queue.Queue], one per connected websocket


class SessionManager:
    def __init__(self):
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()

    def create_session(self, request_text: str) -> str:
        session_id = uuid.uuid4().hex[:12]
        workspace_root = f"{SESSIONS_ROOT}/{session_id}"

        session = Session(id=session_id, request=request_text, workspace_root=workspace_root)
        with self._lock:
            self._sessions[session_id] = session

        thread = threading.Thread(target=self._run_session, args=(session,), daemon=True)
        thread.start()
        return session_id

    def create_demo_verification_session(self) -> str:
        """
        E2B-only browser verification demo — no AI provider key required.
        Exercises sandbox create, app start, test flow, report, and evidence sync.
        """
        session_id = uuid.uuid4().hex[:12]
        workspace_root = f"{SESSIONS_ROOT}/{session_id}"
        session = Session(
            id=session_id,
            request="E2B screenshot demo (no AI)",
            workspace_root=workspace_root,
        )
        with self._lock:
            self._sessions[session_id] = session

        thread = threading.Thread(
            target=self._run_demo_verification,
            args=(session,),
            daemon=True,
        )
        thread.start()
        return session_id

    def _tool_event(self, name: str, tool_input: dict, result: dict) -> list[dict]:
        return [
            {"type": "tool_call", "name": name, "input": tool_input},
            {"type": "tool_result", "name": name, "result": result},
        ]

    def _run_demo_verification(self, session: Session):
        def on_event(event: dict):
            self._emit(session, event)

        def run_tool(name: str, tool_input: dict | None = None) -> dict:
            tool_input = tool_input or {}
            for event in self._tool_event(name, tool_input, {}):
                if event["type"] == "tool_call":
                    on_event(event)
            result = executor.execute(name, tool_input)
            on_event({"type": "tool_result", "name": name, "result": result})
            return result

        try:
            config = load_config()
            if not (config.e2b_api_key or "").strip():
                raise RuntimeError("E2B_API_KEY is not set. Add it to .env — do not paste it in chat.")

            workspace = Workspace(session.workspace_root)
            sandbox = SandboxManager(workspace.root, config, progress_callback=on_event)
            executor = ToolExecutor(workspace, sandbox, config.command_timeout_s)

            create_result = run_tool("create_sandbox", {})
            if not create_result.get("success"):
                raise RuntimeError(create_result.get("error", "create_sandbox failed"))

            file_result = run_tool(
                "create_file",
                {"path": "index.html", "content": _DEMO_HTML},
            )
            if not file_result.get("success", True):
                raise RuntimeError(file_result.get("error", "create_file failed"))

            start_result = run_tool(
                "start_application",
                {"command": "python3 -m http.server 3000", "port": 3000},
            )
            if not start_result.get("success"):
                raise RuntimeError(start_result.get("error", "start_application failed"))

            base_url = start_result.get("internal_url", "http://localhost:3000")
            test_result = run_tool(
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
            if not test_result.get("success"):
                raise RuntimeError(test_result.get("error", "run_test_flow failed"))

            report_result = run_tool(
                "generate_verification_report",
                {"summary": "E2B screenshot demo"},
            )
            if not report_result.get("success"):
                raise RuntimeError(report_result.get("error", "generate_verification_report failed"))

            run_tool("destroy_sandbox", {})

            with self._lock:
                session.status = "done"
                session.result = report_result.get("overall_result", "PASS")
            self._emit(session, {"type": "session_done", "result": session.result})

        except Exception as e:
            try:
                if "sandbox" in locals() and sandbox.is_active and "executor" in locals():
                    executor.execute("destroy_sandbox", {})
            except Exception:
                pass
            with self._lock:
                session.status = "error"
                session.result = str(e)
            self._emit(session, {"type": "session_error", "message": str(e)})

    def get_session(self, session_id: str) -> Optional[Session]:
        with self._lock:
            return self._sessions.get(session_id)

    def subscribe(self, session_id: str) -> Optional[queue.Queue]:
        """
        Returns a queue that receives all future events for this session,
        pre-seeded with everything that already happened before this
        subscriber connected — so a browser tab opened mid-run still sees
        the full history, not just what happens from here on.
        """
        q: queue.Queue = queue.Queue()
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None

            for event in session.events:
                q.put(event)

            if session.status == "running":
                session.subscribers.append(q)
            else:
                # Session already finished before this subscriber connected —
                # give it the closing event immediately so the stream ends cleanly.
                q.put({"type": "session_done" if session.status == "done" else "session_error", "result": session.result})

        return q

    def _emit(self, session: Session, event: dict):
        with self._lock:
            session.events.append(event)
            if event.get("type") == "tool_result" and event.get("name") == "generate_verification_report":
                result = event.get("result") or {}
                if result.get("success") and "machine_readable" in result:
                    session.verification_result = result["machine_readable"]
            for q in session.subscribers:
                q.put(event)

    def _run_session(self, session: Session):
        def on_event(event: dict):
            self._emit(session, event)

        try:
            config = load_config()
            workspace = Workspace(session.workspace_root)
            provider = get_provider(config)
            sandbox = SandboxManager(workspace.root, config, progress_callback=on_event)
            debugging_agent = DebuggingAgent(provider, workspace, config.debug_agent_max_iterations)
            repair_loop = TestRepairLoop(sandbox, debugging_agent, config.max_repair_attempts)
            executor = ToolExecutor(workspace, sandbox, config.command_timeout_s, repair_loop=repair_loop)
            controller = AgentController(config, provider, executor, sandbox)

            result = controller.run(session.request, on_event=on_event)

            with self._lock:
                session.status = "done"
                session.result = result
            self._emit(session, {"type": "session_done", "result": result})

        except Exception as e:
            with self._lock:
                session.status = "error"
                session.result = str(e)
            self._emit(session, {"type": "session_error", "message": str(e)})