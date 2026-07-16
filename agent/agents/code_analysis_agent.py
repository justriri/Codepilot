"""
Code Analysis Agent.

Powers "Agent Interface Mode": a developer submits a code snippet, gets
back the full structured contract:

{
  "issues_found": [],
  "severity": "",
  "explanation": "",
  "suggested_fix": "",
  "rewritten_code": "",
  "tests_generated": [],
  "verification_status": ""
}

Deliberately a NEW, separate class from DebuggingAgent — not a
refactor of it. DebuggingAgent's job is multi-turn, tool-driven
exploration of a real project. This agent's job is single-shot,
structured analysis of one submitted snippet with a fixed output
contract.
"""

from agent.sandbox.manager import SandboxManager
from agent.tools import filesystem
from agent.workspace import Workspace
from providers.base_provider import BaseProvider, ProviderError


class CodeAnalysisAgent:

    def __init__(self, provider: BaseProvider):
        self.provider = provider

    # ------------------------------------------------------------------
    # Individual operations
    # ------------------------------------------------------------------

    def analyze(self, code: str, language: str = None) -> dict:
        return self.provider.analyze_code(code, language)

    def explain(self, code: str, error_message: str, language: str = None) -> dict:
        return self.provider.explain_error(code, error_message, language)

    def suggest_fix(self, code: str, issue_description: str, language: str = None) -> dict:
        return self.provider.suggest_fix(code, issue_description, language)

    def rewrite(self, code: str, fix_description: str, language: str = None) -> dict:
        return self.provider.rewrite_code(code, fix_description, language)

    def generate_tests(self, code: str, language: str = None) -> dict:
        return self.provider.generate_tests(code, language)

    # ------------------------------------------------------------------
    # Sandbox verification
    # ------------------------------------------------------------------

    def verify(
        self,
        code: str,
        filename: str,
        verify_command: str,
        workspace_root: str,
        timeout: int = 30,
    ) -> dict:
        """
        Runs code inside a fresh Docker sandbox and executes verify_command.
        """

        workspace = Workspace(workspace_root)

        filesystem.create_file(
            workspace,
            filename,
            code
        )

        sandbox = SandboxManager(
            workspace.root,
            self._sandbox_config()
        )

        create_result = sandbox.create()

        if not create_result.get("success"):
            return {
                "status": "error",
                "detail": f"Could not start sandbox: {create_result.get('error')}"
            }

        try:
            exec_result = sandbox.exec_command(
                verify_command,
                timeout=timeout
            )

        finally:
            sandbox.destroy()

        status = (
            "passed"
            if exec_result.get("success")
            else "failed"
        )

        return {
            "status": status,
            "exit_code": exec_result.get("exit_code"),
            "stdout": exec_result.get("stdout", ""),
            "stderr": exec_result.get("stderr", ""),
        }

    # ------------------------------------------------------------------
    # Full pipeline
    # ------------------------------------------------------------------

    def full_pipeline(
        self,
        code: str,
        language: str = None,
        verify_command: str = None,
        verify_filename: str = None,
        workspace_root: str = None,
    ) -> dict:
        """
        Developer Code
            ↓
        Analysis
            ↓
        Suggested Fix
            ↓
        Rewrite
            ↓
        Test Generation
            ↓
        Sandbox Verification
        """

        try:
            analysis = self.analyze(
                code,
                language
            )

        except ProviderError as e:
            return self._error_result(
                f"Analysis failed: {e}"
                )

        issues = analysis.get(
            "issues_found",
            []
        )

        severity = analysis.get(
            "severity",
            "none"
        )

        explanation = analysis.get(
            "explanation",
            ""
        )

        if not issues:
            return {
                "issues_found": [],
                "severity": severity or "none",
                "explanation": explanation or "No issues found.",
                "suggested_fix": "",
                "rewritten_code": "",
                "tests_generated": [],
                "verification_status": "no_issues_found",
            }

        try:
            fix = self.suggest_fix(
                code,
                explanation or "; ".join(issues),
                language
            )

            suggested_fix = fix.get(
                "suggested_fix",
                ""
            )

            rewrite = self.rewrite(
                code,
                suggested_fix,
                language
            )

            rewritten_code = rewrite.get(
                "rewritten_code",
                ""
            )

            tests = self.generate_tests(
                rewritten_code or code,
                language
            )

            tests_generated = tests.get(
                "tests_generated",
                []
            )

        except ProviderError as e:
            return self._error_result(
                f"Fix generation failed: {e}",
                partial={
                    "issues_found": issues,
                    "severity": severity,
                    "explanation": explanation,
                }
            )

        verification_status = "not_run"

        if verify_command and rewritten_code:

            root = (
                workspace_root
                or "./verification_workspaces/tmp"
            )

            filename = (
                verify_filename
                or "solution.py"
            )

            try:
                result = self.verify(
                    rewritten_code,
                    filename,
                    verify_command,
                    root
                )

                verification_status = result["status"]

            except Exception as e:
                verification_status = f"error: {e}"

        return {
            "issues_found": issues,
            "severity": severity,
            "explanation": explanation,
            "suggested_fix": suggested_fix,
            "rewritten_code": rewritten_code,
            "tests_generated": tests_generated,
            "verification_status": verification_status,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _error_result(
        message: str,
        partial: dict = None
    ) -> dict:

        result = {
            "issues_found": [],
            "severity": "unknown",
            "explanation": message,
            "suggested_fix": "",
            "rewritten_code": "",
            "tests_generated": [],
            "verification_status": "error",
        }

        if partial:
            result.update(partial)

        return result

    @staticmethod
    def _sandbox_config():

        from agent.config import load_config

        return load_config()