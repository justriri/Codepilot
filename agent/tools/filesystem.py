"""
Filesystem tool implementations.

Each function here is the actual logic behind one tool the agent can call.
They take a Workspace instance (so they only ever touch the sandboxed
project directory) plus tool-specific arguments, and return a plain dict
that gets JSON-serialized back to the model as a tool_result.
"""

import os

from agent.workspace import Workspace


def create_file(workspace: Workspace, path: str, content: str = "") -> dict:
    """Create a new file (or overwrite an existing one) with the given content."""
    full_path = workspace.resolve(path)

    parent_dir = os.path.dirname(full_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)

    return {"success": True, "path": path, "bytes_written": len(content.encode("utf-8"))}


def read_file(workspace: Workspace, path: str) -> dict:
    """Read and return the contents of an existing file."""
    full_path = workspace.resolve(path)

    if not os.path.isfile(full_path):
        return {"success": False, "error": f"File not found: {path}"}

    with open(full_path, "r", encoding="utf-8") as f:
        content = f.read()

    return {"success": True, "path": path, "content": content}


def list_files(workspace: Workspace) -> dict:
    """List every file currently in the project workspace."""
    return {"success": True, "files": workspace.tree()}
