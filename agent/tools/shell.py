"""
DEPRECATED as of the sandbox layer.

This local-subprocess implementation is no longer wired into
ToolExecutor — run_command executes inside the E2B cloud sandbox via
SandboxManager.exec_command instead (see agent/sandbox/manager.py).

Kept in the repo only as a reference for local execution without a
cloud sandbox. Do not re-wire this for anything beyond trusted local use —
it has none of the sandbox's resource limits or isolation.
"""

import subprocess

from agent.workspace import Workspace


def run_command(workspace: Workspace, command: str, timeout: int = 30) -> dict:
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=workspace.root,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "success": result.returncode == 0,
            "exit_code": result.returncode,
            # Truncate long output so a noisy command doesn't blow the model's context
            "stdout": result.stdout[-4000:],
            "stderr": result.stderr[-4000:],
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"Command timed out after {timeout}s: {command}"}
    except Exception as e:
        return {"success": False, "error": str(e)}
