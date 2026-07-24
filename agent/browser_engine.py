"""
Browser engine selection for Playwright verification.

Supports explicit engine choice (firefox, chromium, webkit) or auto mode
with an environment-aware fallback chain.
"""

from __future__ import annotations

import os

VALID_ENGINES = frozenset({"firefox", "chromium", "webkit", "auto"})
FALLBACK_ORDER_E2B = ("firefox", "chromium", "webkit")
FALLBACK_ORDER_OPT = ("chromium", "firefox", "webkit")


def normalize_engine(value: str | None) -> str:
    engine = (value or "auto").strip().lower()
    if engine not in VALID_ENGINES:
        raise ValueError(
            f"Invalid BROWSER_ENGINE '{value}'. "
            f"Use one of: {', '.join(sorted(VALID_ENGINES))}"
        )
    return engine


def resolve_fallback_order(requested: str, *, has_opt_tools: bool) -> list[str]:
    """
    Return ordered engine names to try.

    auto:
      - Custom/Docker template (/opt/agent-tools): chromium first
      - Default E2B VM: firefox first (chromium headless_shell is unreliable)
    """
    if requested != "auto":
        return [requested]

    if has_opt_tools:
        return list(FALLBACK_ORDER_OPT)
    return list(FALLBACK_ORDER_E2B)


def launch_args(engine: str) -> list[str]:
    if engine == "chromium":
        return ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
    return []


def install_command(engine: str) -> str:
    return (
        f"(sudo python3 -m playwright install-deps {engine} "
        f"|| python3 -m playwright install-deps {engine}) && "
        f"python3 -m playwright install {engine}"
    )


def probe_command(engine: str, *, python_bin: str = "python3") -> str:
    args = launch_args(engine)
    args_repr = repr(args)
    return (
        f"{python_bin} -c \""
        "from playwright.sync_api import sync_playwright; "
        "p=sync_playwright().start(); "
        f"b=p.{engine}.launch(headless=True, args={args_repr}); "
        "pg=b.new_page(); pg.goto('about:blank', timeout=15000); "
        "b.close(); p.stop(); print('ok')"
        "\" 2>&1"
    )


def read_engine_from_workspace(workspace_root: str) -> str | None:
    path = os.path.join(workspace_root, ".sandbox", "browser_engine")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            value = f.read().strip().lower()
        return value if value in VALID_ENGINES - {"auto"} else None
    except OSError:
        return None
