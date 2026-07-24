"""Browser engine helpers used inside the sandbox VM (no agent/ imports)."""

import os

VALID = frozenset({"firefox", "chromium", "webkit"})


def launch_args(engine: str) -> list[str]:
    if engine == "chromium":
        return ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
    return []


def read_engine_from_workspace(workspace_root: str) -> str | None:
    path = os.path.join(workspace_root, ".sandbox", "browser_engine")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            value = f.read().strip().lower()
        return value if value in VALID else None
    except OSError:
        return None
