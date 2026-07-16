"""
Execution Loop.

Handles single-code verification workflow:

Developer submits code
        |
        v
Analyze code
        |
        v
Generate fix
        |
        v
Generate tests
        |
        v
Build test plan
        |
        v
Run tests in isolated sandbox
        |
        v
Repair failures (bounded retries)
        |
        v
Return verified result
"""

import uuid

from agent.agents import test_plan as test_plan_module
from agent.agents.code_analysis_agent import CodeAnalysisAgent
from agent.sandbox.manager import SandboxManager
from agent.tools import filesystem
from agent.workspace import Workspace
from providers.base_provider import ProviderError


class ExecutionLoop:

    def __init__(
        self,
        code_analysis_agent: CodeAnalysisAgent,
        max_repair_attempts: int = 3,
    ):
        self.agent = code_analysis_agent
        self.max_repair_attempts = max_repair_attempts


    def run(
        self,
        code: str,
        language: str,
        workspace_root: str = None,
    ) -> dict:

        try:
            analysis = self.agent.analyze(
                code,
                language,
            )

        except ProviderError as e:

            return self._result(
                status="error",
                detail=f"Analysis failed: {e}",
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

            return self._result(
                status="no_issues_found",
                issues_found=[],
                severity=severity,
                explanation=(
                    explanation
                    or "No issues found."
                ),
                rewritten_code=code,
            )


        current_code = code
        fix = {
            "suggested_fix": ""
        }


        try:

            fix = self.agent.suggest_fix(
                code,
                explanation or "; ".join(issues),
                language,
            )


            rewrite = self.agent.rewrite(
                code,
                fix.get(
                    "suggested_fix",
                    "",
                ),
                language,
            )


            current_code = (
                rewrite.get(
                    "rewritten_code",
                    ""
                )
                or code
            )


            tests = self.agent.generate_tests(
                current_code,
                language,
            )


            tests_generated = tests.get(
                "tests_generated",
                []
            )


        except ProviderError as e:

            return self._result(
                status="error",
                detail=f"Fix generation failed: {e}",
                issues_found=issues,
                severity=severity,
                explanation=explanation,
            )



        plan = test_plan_module.build_test_plan(
            current_code,
            tests_generated,
            language,
        )


        if not plan.get("success"):

            return self._result(
                status="error",
                detail=plan.get(
                    "error",
                    "Could not create test plan",
                ),
                issues_found=issues,
                severity=severity,
                explanation=explanation,
                suggested_fix=fix.get(
                    "suggested_fix",
                    "",
                ),
                rewritten_code=current_code,
                tests_generated=tests_generated,
            )


        root = (
            workspace_root
            or f"./execution_workspaces/{uuid.uuid4().hex[:12]}"
        )


        repair_log = []

        attempts_used = 0


        exec_result = self.run_test_plan(
            plan,
            root,
            attempt=0,
        )
        while (
            not exec_result.get("success")
            and attempts_used < self.max_repair_attempts
        ):

            attempts_used += 1


            failure_detail = (
                "Test execution failed.\n"
                f"stdout:\n{exec_result.get('stdout', '')}\n"
                f"stderr:\n{exec_result.get('stderr', '')}"
            )


            try:

                fix = self.agent.suggest_fix(
                    current_code,
                    failure_detail,
                    language,
                )


                rewrite = self.agent.rewrite(
                    current_code,
                    fix.get(
                        "suggested_fix",
                        "",
                    ),
                    language,
                )


                current_code = (
                    rewrite.get(
                        "rewritten_code",
                        "",
                    )
                    or current_code
                )


            except ProviderError as e:

                repair_log.append(
                    {
                        "attempt": attempts_used,
                        "error": str(e),
                    }
                )

                break



            plan = test_plan_module.build_test_plan(
                current_code,
                tests_generated,
                language,
            )


            exec_result = self.run_test_plan(
                plan,
                root,
                attempt=attempts_used,
            )


            repair_log.append(
                {
                    "attempt": attempts_used,
                    "suggested_fix": fix.get(
                        "suggested_fix",
                        "",
                    ),
                    "test_result": {
                        "success": exec_result.get(
                            "success"
                        ),
                        "exit_code": exec_result.get(
                            "exit_code"
                        ),
                        "stdout": exec_result.get(
                            "stdout",
                            "",
                        ),
                        "stderr": exec_result.get(
                            "stderr",
                            "",
                        ),
                    },
                }
            )


        return self._result(
            status=(
                "passed"
                if exec_result.get("success")
                else "failed"
            ),
            issues_found=issues,
            severity=severity,
            explanation=explanation,
            suggested_fix=fix.get(
                "suggested_fix",
                "",
            ),
            rewritten_code=current_code,
            tests_generated=tests_generated,
            repair_attempts=repair_log,
            repair_attempts_used=attempts_used,
            test_execution={
                "success": exec_result.get(
                    "success"
                ),
                "exit_code": exec_result.get(
                    "exit_code"
                ),
                "stdout": exec_result.get(
                    "stdout",
                    "",
                ),
                "stderr": exec_result.get(
                    "stderr",
                    "",
                ),
            },
        )



    def run_test_plan(
        self,
        plan: dict,
        workspace_root: str,
        attempt: int = 0,
    ) -> dict:

        attempt_root = (
            f"{workspace_root}/attempt_{attempt}"
        )

        workspace = Workspace(
            attempt_root
        )


        for filename, content in plan["files"].items():

            filesystem.create_file(
                workspace,
                filename,
                content,
            )


        sandbox = SandboxManager(
            workspace.root,
            self._sandbox_config(),
        )


        create_result = sandbox.create()
        if not create_result.get("success"):

            return {
                "success": False,
                "error": (
                    "Could not start sandbox: "
                    f"{create_result.get('error')}"
                ),
            }


        try:

            return sandbox.exec_command(
                plan["run_command"],
                timeout=30,
            )

        finally:

            sandbox.destroy()



    @staticmethod
    def _sandbox_config():

        from agent.config import load_config

        return load_config()



    @staticmethod
    def _result(
        status,
        issues_found=None,
        severity="",
        explanation="",
        suggested_fix="",
        rewritten_code="",
        tests_generated=None,
        repair_attempts=None,
        repair_attempts_used=0,
        test_execution=None,
        detail=None,
    ) -> dict:


        result = {
            "issues_found": issues_found or [],
            "severity": severity,
            "explanation": explanation,
            "suggested_fix": suggested_fix,
            "rewritten_code": rewritten_code,
            "tests_generated": tests_generated or [],
            "verification_status": status,
            "repair_attempts": repair_attempts or [],
            "repair_attempts_used": repair_attempts_used,
        }


        if test_execution is not None:

            result["test_execution"] = test_execution


        if detail is not None:

            result["detail"] = detail


        return result