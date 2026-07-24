"""
Browser Controller.

A small, reusable wrapper around Playwright's sync API providing the
core primitives needed to drive a browser against a running application.
Runs INSIDE the E2B cloud sandbox VM, in the same network namespace as
the app under test, so open_browser(url) reaches the app directly via
its internal port. When /opt/agent-tools/ is present (custom E2B template),
scripts are loaded from there; otherwise they are synced from the repo
and Playwright is installed on first run.

Public API (the literal requested interface):
    open_browser(url)
    click_element(selector)
    fill_input(selector, text)
    take_screenshot(filename)
    close_browser()

A handful of additional helper methods (is_visible, get_text,
wait_for_selector, get_last_status_code, get_console_errors) are also
provided because TestingAgent needs to make assertions, not just perform
actions — but the five methods above are the primary interface this
module exists to provide, and each also works standalone.

All screenshot/video paths are returned relative to the project
workspace root (e.g. '.sandbox/evidence/foo.png'), matching the
convention the rest of the system already uses for evidence references.
"""

import glob
import os
import shutil

from browser_utils import launch_args, read_engine_from_workspace


class BrowserController:
    def __init__(
        self,
        workspace_root: str | None = None,
        evidence_subdir: str = ".sandbox/evidence",
        record_video: bool = False,
    ):
        if not workspace_root or workspace_root == "/workspace":
            workspace_root = os.environ.get("WORKSPACE_ROOT", os.getcwd())
        self.workspace_root = workspace_root
        self.evidence_subdir = evidence_subdir
        self.evidence_dir_abs = os.path.join(workspace_root, evidence_subdir)
        os.makedirs(self.evidence_dir_abs, exist_ok=True)

        self.record_video = record_video
        self._video_tmp_dir = os.path.join(self.evidence_dir_abs, "_video_tmp")

        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

        self.last_status_code = None
        self.console_errors = []
        self.video_path = None  # relative path, populated by close_browser() if recording

    # ------------------------------------------------------------------
    # Lazy startup — the browser process isn't launched until the first
    # real action needs it.
    # ------------------------------------------------------------------

    def _ensure_started(self):
        if self._page is not None:
            return

        from playwright.sync_api import sync_playwright

        engine = (
            os.environ.get("BROWSER_ENGINE", "").strip().lower()
            or read_engine_from_workspace(self.workspace_root)
            or "firefox"
        )
        if engine not in ("firefox", "chromium", "webkit"):
            engine = "firefox"

        self._playwright = sync_playwright().start()
        browser_type = getattr(self._playwright, engine)
        launch_kwargs = {"headless": True}
        args = launch_args(engine)
        if args:
            launch_kwargs["args"] = args
        self._browser = browser_type.launch(**launch_kwargs)
        self._browser_engine = engine

        context_kwargs = {}
        if self.record_video:
            os.makedirs(self._video_tmp_dir, exist_ok=True)
            context_kwargs["record_video_dir"] = self._video_tmp_dir
            context_kwargs["record_video_size"] = {"width": 1280, "height": 720}

        self._context = self._browser.new_context(**context_kwargs)
        self._page = self._context.new_page()
        self._page.on(
            "console",
            lambda msg: self.console_errors.append(msg.text) if msg.type == "error" else None,
        )

    # ------------------------------------------------------------------
    # The 5 core primitives
    # ------------------------------------------------------------------

    def open_browser(self, url: str, timeout_ms: int = 15000) -> dict:
        """Launch the browser if needed, and navigate to `url`."""
        self._ensure_started()
        try:
            response = self._page.goto(url, timeout=timeout_ms)
        except Exception as e:
            return {"success": False, "error": f"Failed to open '{url}': {e}"}

        self.last_status_code = response.status if response else None
        return {"success": True, "url": url, "status_code": self.last_status_code}

    def click_element(self, selector: str, timeout_ms: int = 10000) -> dict:
        self._ensure_started()
        try:
            self._page.locator(selector).first.click(timeout=timeout_ms)
        except Exception as e:
            return {"success": False, "error": f"Failed to click '{selector}': {e}"}
        return {"success": True, "selector": selector}

    def fill_input(self, selector: str, text: str, timeout_ms: int = 10000) -> dict:
        self._ensure_started()
        try:
            self._page.locator(selector).first.fill(text, timeout=timeout_ms)
        except Exception as e:
            return {"success": False, "error": f"Failed to fill '{selector}': {e}"}
        return {"success": True, "selector": selector}

    def take_screenshot(self, filename: str) -> dict:
        """
        Save a screenshot to <evidence_dir>/<filename>. Safe to call even
        if the browser never started (returns success: False rather than
        raising) — evidence capture failing should never mask or crash
        out of an actual test result.
        """
        if self._page is None:
            return {"success": False, "error": "Browser not open — call open_browser first."}

        abs_path = os.path.join(self.evidence_dir_abs, filename)
        try:
            self._page.screenshot(path=abs_path)
        except Exception as e:
            return {"success": False, "error": str(e)}

        return {"success": True, "path": os.path.join(self.evidence_subdir, filename)}

    def close_browser(self) -> dict:
        """Close the browser and finalize the video recording, if any.
        Safe to call multiple times or even if the browser never opened."""
        try:
            if self._context:
                self._context.close()  # video file is only finalized once the context closes
            if self._browser:
                self._browser.close()
            if self._playwright:
                self._playwright.stop()
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            if self.record_video:
                self._finalize_video()
            self._browser = None
            self._context = None
            self._page = None
            self._playwright = None

        return {"success": True}

    def _finalize_video(self):
        candidates = glob.glob(os.path.join(self._video_tmp_dir, "*.webm"))
        if candidates:
            final_abs = os.path.join(self.evidence_dir_abs, "session.webm")
            shutil.move(candidates[0], final_abs)
            self.video_path = os.path.join(self.evidence_subdir, "session.webm")
        shutil.rmtree(self._video_tmp_dir, ignore_errors=True)

    # ------------------------------------------------------------------
    # Assertion helpers (needed by TestingAgent to identify failures,
    # beyond the five core action primitives above)
    # ------------------------------------------------------------------

    def is_visible(self, selector: str) -> bool:
        self._ensure_started()
        try:
            return self._page.locator(selector).first.is_visible()
        except Exception:
            return False

    def get_text(self, selector: str, timeout_ms: int = 10000) -> str:
        self._ensure_started()
        return self._page.locator(selector).first.inner_text(timeout=timeout_ms)

    def wait_for_selector(self, selector: str, timeout_ms: int = 10000) -> dict:
        self._ensure_started()
        try:
            self._page.wait_for_selector(selector, timeout=timeout_ms)
        except Exception as e:
            return {"success": False, "error": str(e)}
        return {"success": True}

    def get_last_status_code(self):
        return self.last_status_code

    def get_console_errors(self) -> list:
        return list(self.console_errors)
