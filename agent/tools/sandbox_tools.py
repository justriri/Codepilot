"""
Sandbox tool implementations.

Thin adapters between the agent's tool_use calls and the SandboxManager.
Kept separate from manager.py so the manager stays a plain, reusable
Python class (testable on its own) while this file only handles the
"unpack tool_input, call the manager, handle SandboxError" boilerplate.
"""

from agent.sandbox.manager import SandboxManager, SandboxError


def create_sandbox(manager: SandboxManager, tool_input: dict) -> dict:
    return manager.create()


def install_dependencies(manager: SandboxManager, tool_input: dict) -> dict:
    try:
        return manager.exec_command(
            tool_input["command"], tool_input.get("timeout", 180)
        )
    except SandboxError as e:
        return {"success": False, "error": str(e)}


def start_application(manager: SandboxManager, tool_input: dict) -> dict:
    try:
        return manager.start_application(
            tool_input["command"], tool_input.get("port")
        )
    except SandboxError as e:
        return {"success": False, "error": str(e)}


def stop_application(manager: SandboxManager, tool_input: dict) -> dict:
    try:
        return manager.stop_application()
    except SandboxError as e:
        return {"success": False, "error": str(e)}


def destroy_sandbox(manager: SandboxManager, tool_input: dict) -> dict:
    return manager.destroy()


def run_test_flow(manager: SandboxManager, tool_input: dict) -> dict:
    try:
        return manager.run_test_flow(
            tool_input["base_url"],
            tool_input.get("steps", []),
            tool_input.get("record_video", False),
            tool_input.get("timeout", 90),
        )
    except SandboxError as e:
        return {"success": False, "error": str(e)}


def generate_verification_report(manager: SandboxManager, tool_input: dict) -> dict:
    return manager.generate_report(tool_input.get("summary", ""))
