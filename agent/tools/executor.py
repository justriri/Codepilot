"""
Tool execution layer.

Single dispatch point between model tool calls and actual implementations.
All commands execute inside the sandbox container.
"""

from agent.sandbox.manager import SandboxManager, SandboxError
from agent.tools import filesystem, sandbox_tools
from agent.workspace import Workspace


class ToolExecutor:

    def __init__(
        self,
        workspace: Workspace,
        sandbox_manager: SandboxManager,
        command_timeout_s: int = 30,
        repair_loop=None,
    ):
        self.workspace = workspace
        self.sandbox = sandbox_manager
        self.command_timeout_s = command_timeout_s
        self.repair_loop = repair_loop

        self._registry = {
            "create_file": self._create_file,
            "read_file": self._read_file,
            "list_files": self._list_files,
            "run_command": self._run_command,
            "create_sandbox": self._create_sandbox,
            "install_dependencies": self._install_dependencies,
            "start_application": self._start_application,
            "stop_application": self._stop_application,
            "destroy_sandbox": self._destroy_sandbox,
            "run_test_flow": self._run_test_flow,
            "generate_verification_report": self._generate_verification_report,
        }

    def execute(
        self,
        tool_name: str,
        tool_input: dict
    ) -> dict:

        handler = self._registry.get(tool_name)

        if handler is None:
            return {
                "success": False,
                "error": f"Unknown tool: {tool_name}"
            }

        try:
            return handler(tool_input)

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }


    # -------------------------
    # Filesystem tools
    # -------------------------

    def _create_file(self, tool_input: dict) -> dict:
        return filesystem.create_file(
            self.workspace,
            tool_input["path"],
            tool_input.get("content", "")
        )


    def _read_file(self, tool_input: dict) -> dict:
        return filesystem.read_file(
            self.workspace,
            tool_input["path"]
        )


    def _list_files(self, tool_input: dict) -> dict:
        return filesystem.list_files(
            self.workspace
        )


    # -------------------------
    # Sandbox tools
    # -------------------------

    def _run_command(self, tool_input: dict) -> dict:
        try:
            return self.sandbox.exec_command(
                tool_input["command"],
                tool_input.get(
                    "timeout",
                    self.command_timeout_s
                )
            )

        except SandboxError as e:
            return {
                "success": False,
                "error": str(e)
            }


    def _create_sandbox(self, tool_input: dict) -> dict:
        return sandbox_tools.create_sandbox(
            self.sandbox,
            tool_input
        )


    def _install_dependencies(self, tool_input: dict) -> dict:
        return sandbox_tools.install_dependencies(
            self.sandbox,
            tool_input
        )


    def _start_application(self, tool_input: dict) -> dict:
        return sandbox_tools.start_application(
            self.sandbox,
            tool_input
        )


    def _stop_application(self, tool_input: dict) -> dict:
        return sandbox_tools.stop_application(
            self.sandbox,
            tool_input
        )


    def _destroy_sandbox(self, tool_input: dict) -> dict:
        return sandbox_tools.destroy_sandbox(
            self.sandbox,
            tool_input
        )


    def _run_test_flow(self, tool_input: dict) -> dict:

        if self.repair_loop is not None:
            return self.repair_loop.run(tool_input)

        return sandbox_tools.run_test_flow(
            self.sandbox,
            tool_input
        )


    def _generate_verification_report(self, tool_input: dict) -> dict:
        return sandbox_tools.generate_verification_report(
            self.sandbox,
            tool_input
        )