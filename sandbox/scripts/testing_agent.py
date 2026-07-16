"""
Testing Agent.

Executes an ordered list of test steps against a running application by
driving a BrowserController through them, recording pass/fail per step.
A screenshot is captured after every step for full evidence, plus an
extra, distinctly-named screenshot specifically when a step fails, so
failure evidence is always easy to find without scanning the whole
sequence.

Step format (the vocabulary used throughout the agent's tools):
    {"action": "navigate", "path": "/"}
    {"action": "click", "selector": "text=Sign Up"}
    {"action": "fill", "selector": "#email", "value": "test@example.com"}
    {"action": "wait_for_selector", "selector": "#dashboard"}
    {"action": "assert_visible", "selector": "#dashboard"}
    {"action": "assert_text", "selector": "h1", "expected": "Welcome"}
    {"action": "assert_status", "expected": 200}
    {"action": "screenshot", "label": "custom-name"}

Example flow matching "Open app -> Click Sign Up -> Enter email ->
Submit form -> Confirm dashboard loads":
    [
        {"action": "navigate", "path": "/"},
        {"action": "click", "selector": "text=Sign Up"},
        {"action": "fill", "selector": "#email", "value": "test@example.com"},
        {"action": "click", "selector": "button[type=submit]"},
        {"action": "wait_for_selector", "selector": "#dashboard"},
        {"action": "assert_visible", "selector": "#dashboard"},
    ]
"""


class TestingAgent:
    def __init__(self, browser_controller, base_url: str):
        self.browser = browser_controller
        self.base_url = base_url.rstrip("/")
        self.results = []  # ordered list of per-step outcomes

    def run(self, steps: list) -> list:
        for i, step in enumerate(steps):
            self.results.append(self._run_step(i, step))
        return self.results

    def _run_step(self, index: int, step: dict) -> dict:
        action = step.get("action")
        selector = step.get("selector")
        expected = step.get("expected")
        passed = False
        detail = ""

        try:
            if action == "navigate":
                url = f"{self.base_url}{step.get('path', '/')}"
                result = self.browser.open_browser(url)
                passed = result.get("success", False)
                detail = (
                    f"Opened {url} (status {result.get('status_code')})"
                    if passed
                    else result.get("error", "Navigation failed")
                )

            elif action == "click":
                result = self.browser.click_element(selector)
                passed = result.get("success", False)
                detail = f"Clicked '{selector}'" if passed else result.get("error", "Click failed")

            elif action == "fill":
                result = self.browser.fill_input(selector, step.get("value", ""))
                passed = result.get("success", False)
                detail = f"Filled '{selector}'" if passed else result.get("error", "Fill failed")

            elif action == "wait_for_selector":
                result = self.browser.wait_for_selector(selector, step.get("timeout_ms", 10000))
                passed = result.get("success", False)
                detail = f"'{selector}' appeared" if passed else result.get("error", "Timed out waiting")

            elif action == "assert_visible":
                passed = self.browser.is_visible(selector)
                detail = "Element is visible" if passed else "Element not visible or not found"

            elif action == "assert_text":
                try:
                    actual = self.browser.get_text(selector)
                    passed = str(expected) in actual
                    detail = f"Got '{actual}', expected it to contain '{expected}'"
                except Exception as e:
                    detail = f"Error reading text from '{selector}': {e}"

            elif action == "assert_status":
                actual_status = self.browser.get_last_status_code()
                passed = actual_status == expected
                detail = f"Last status was {actual_status}, expected {expected}"

            elif action == "screenshot":
                passed = True
                detail = "Manual screenshot requested"

            else:
                detail = f"Unknown action: {action}"

        except Exception as e:
            detail = f"{type(e).__name__}: {e}"

        label = step.get("label") or f"step{index}_{action or 'unknown'}"
        screenshot_path = self._capture(label, is_failure=not passed)

        return {
            "index": index,
            "action": action,
            "selector": selector,
            "expected": expected,
            "passed": passed,
            "detail": detail,
            "screenshot": screenshot_path,
        }

    def _capture(self, label: str, is_failure: bool):
        # Always capture one screenshot per step for full evidence...
        result = self.browser.take_screenshot(f"{label}.png")

        # ...and an additional, distinctly-named screenshot specifically
        # when a step fails, so failure evidence is easy to find without
        # scanning the whole sequence.
        if is_failure:
            self.browser.take_screenshot(f"FAILURE_{label}.png")

        return result.get("path") if result.get("success") else None

    @property
    def passed_count(self) -> int:
        return sum(1 for r in self.results if r["passed"])

    @property
    def failed_count(self) -> int:
        return sum(1 for r in self.results if not r["passed"])

    @property
    def all_passed(self) -> bool:
        return bool(self.results) and self.failed_count == 0
