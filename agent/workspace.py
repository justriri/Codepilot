"""
Workspace layer.

Represents the project directory the agent is allowed to operate in.
This is a LOCAL filesystem stand-in for the isolated sandbox described
in the broader architecture (e.g. E2B / Daytona). It is NOT a security
boundary against malicious code — it only prevents accidental path
traversal outside the intended project folder during local development.

When you move to a real sandbox provider, this class's interface
(resolve, tree) is what the sandbox-backed implementation should
preserve, so the rest of the codebase doesn't need to change.
"""

import os


class Workspace:
    def __init__(self, root: str):
        self.root = os.path.abspath(root)
        os.makedirs(self.root, exist_ok=True)

    def resolve(self, relative_path: str) -> str:
        """
        Resolve a relative path against the workspace root.
        Raises if the resolved path would escape the workspace
        (blocks things like '../../etc/passwd').
        """
        candidate = os.path.abspath(os.path.join(self.root, relative_path))
        if not (candidate == self.root or candidate.startswith(self.root + os.sep)):
            raise ValueError(f"Path '{relative_path}' escapes the workspace root.")
        return candidate

    def tree(self) -> list[str]:
        """Return all file paths in the workspace, relative to its root."""
        results = []
        for dirpath, dirnames, filenames in os.walk(self.root):
            # Skip common noise directories so the agent isn't overwhelmed
            dirnames[:] = [d for d in dirnames if d not in (".git", "node_modules", "__pycache__")]
            for f in filenames:
                full = os.path.join(dirpath, f)
                results.append(os.path.relpath(full, self.root))
        return sorted(results)
