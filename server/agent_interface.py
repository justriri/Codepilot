"""
Mode 1: Agent Interface.

Standalone endpoints for submitting a code snippet and getting back
analysis, explanations, fixes, rewrites, and optional sandbox
verification. Stateless — each call is independent, no session/
conversation state carried between requests (unlike /api/sessions,
which runs the full autonomous AgentController loop to build a whole
project). This mode is for "analyze this one snippet" usage.

Endpoints:
    POST /api/agent-interface/analyze      -> issues_found, severity, explanation
    POST /api/agent-interface/explain      -> explanation for a given error
    POST /api/agent-interface/suggest-fix  -> suggested_fix, confidence
    POST /api/agent-interface/rewrite      -> rewritten_code, explanation
    POST /api/agent-interface/verify       -> runs code in a real sandbox, returns pass/fail
    POST /api/agent-interface/full         -> the full structured contract, composing all of the above
"""

import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from providers.base_provider import ProviderError
from server.dependencies import code_analysis_agent, execution_loop


router = APIRouter(
    prefix="/api/agent-interface",
    tags=["agent-interface"],
)


def _call_or_502(fn, *args, **kwargs):
    """
    Runs a CodeAnalysisAgent method, converting ProviderError into
    a proper HTTP 502 instead of an unhandled 500.
    """
    try:
        return fn(*args, **kwargs)

    except ProviderError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Provider error: {e}",
        )


class CodeRequest(BaseModel):
    code: str
    language: Optional[str] = None


class ExplainRequest(BaseModel):
    code: str
    error_message: str
    language: Optional[str] = None


class SuggestFixRequest(BaseModel):
    code: str
    issue_description: str
    language: Optional[str] = None


class RewriteRequest(BaseModel):
    code: str
    fix_description: str
    language: Optional[str] = None


class VerifyRequest(BaseModel):
    code: str
    filename: str
    verify_command: str
    timeout: int = 30


class FullPipelineRequest(BaseModel):
    code: str
    language: Optional[str] = None
    verify_command: Optional[str] = None
    verify_filename: Optional[str] = None


class ExecuteRequest(BaseModel):
    code: str
    language: str


class GenerateTestsRequest(BaseModel):
    code: str
    language: Optional[str] = None


class RunTestsRequest(BaseModel):
    code: str
    tests_generated: list
    language: str



@router.post("/analyze")
def analyze(payload: CodeRequest):
    # #region agent log
    try:
        import json as _json
        open("debug-90c2dc.log", "a", encoding="utf-8").write(_json.dumps({"sessionId": "90c2dc", "hypothesisId": "D", "location": "agent_interface.py:analyze", "message": "analyze endpoint entered", "data": {"code_len": len(payload.code or ""), "language": payload.language}, "timestamp": __import__("time").time() * 1000}) + "\n")
    except Exception:
        pass
    # #endregion
    try:
        result = _call_or_502(
            code_analysis_agent.analyze,
            payload.code,
            payload.language,
        )
        # #region agent log
        try:
            import json as _json
            open("debug-90c2dc.log", "a", encoding="utf-8").write(_json.dumps({"sessionId": "90c2dc", "hypothesisId": "A", "location": "agent_interface.py:analyze:success", "message": "analyze succeeded", "data": {"keys": list(result.keys()) if isinstance(result, dict) else type(result).__name__}, "timestamp": __import__("time").time() * 1000}) + "\n")
        except Exception:
            pass
        # #endregion
        return result
    except Exception as e:
        # #region agent log
        try:
            import json as _json
            open("debug-90c2dc.log", "a", encoding="utf-8").write(_json.dumps({"sessionId": "90c2dc", "hypothesisId": "A", "location": "agent_interface.py:analyze:error", "message": "analyze failed", "data": {"error_type": type(e).__name__, "error": str(e)[:500]}, "timestamp": __import__("time").time() * 1000}) + "\n")
        except Exception:
            pass
        # #endregion
        raise



@router.post("/explain")
def explain(payload: ExplainRequest):
    return _call_or_502(
        code_analysis_agent.explain,
        payload.code,
        payload.error_message,
        payload.language,
    )



@router.post("/suggest-fix")
def suggest_fix(payload: SuggestFixRequest):
    return _call_or_502(
        code_analysis_agent.suggest_fix,
        payload.code,
        payload.issue_description,
        payload.language,
    )



@router.post("/rewrite")
def rewrite(payload: RewriteRequest):
    return _call_or_502(
        code_analysis_agent.rewrite,
        payload.code,
        payload.fix_description,
        payload.language,
    )



@router.post("/verify")
def verify(payload: VerifyRequest):

    workspace_root = (
        f"./verification_workspaces/{uuid.uuid4().hex[:12]}"
    )

    return code_analysis_agent.verify(
        code=payload.code,
        filename=payload.filename,
        verify_command=payload.verify_command,
        workspace_root=workspace_root,
        timeout=payload.timeout,
    )



@router.post("/full")
def full_pipeline(payload: FullPipelineRequest):

    workspace_root = (
        f"./verification_workspaces/{uuid.uuid4().hex[:12]}"
        if payload.verify_command
        else None
    )

    return code_analysis_agent.full_pipeline(
        code=payload.code,
        language=payload.language,
        verify_command=payload.verify_command,
        verify_filename=payload.verify_filename,
        workspace_root=workspace_root,
    )



@router.post("/execute")
def execute(payload: ExecuteRequest):
    """
    Core execution loop:

    analyze
        ->
    generate tests
        ->
    create sandbox
        ->
    execute tests
        ->
    read results
        ->
    suggest fixes
        ->
    retry verification

    See:
    agent/agents/execution_loop.py
    """

    workspace_root = (
        f"./execution_workspaces/{uuid.uuid4().hex[:12]}"
    )

    return execution_loop.run(
        code=payload.code,
        language=payload.language,
        workspace_root=workspace_root,
    )



@router.post("/generate-tests")
def generate_tests(payload: GenerateTestsRequest):

    return _call_or_502(
        code_analysis_agent.generate_tests,
        payload.code,
        payload.language,
    )



@router.post("/run-tests")
def run_tests(payload: RunTestsRequest):
    """
    Builds a test plan from generated tests and executes it once
    inside the E2B cloud sandbox.
    """

    from agent.agents import test_plan as test_plan_module


    plan = test_plan_module.build_test_plan(
        payload.code,
        payload.tests_generated,
        payload.language,
    )


    if not plan.get("success"):
        return {
            "status": "error",
            "detail": plan.get("error"),
            "exit_code": None,
            "stdout": "",
            "stderr": "",
        }


    workspace_root = (
        f"./execution_workspaces/{uuid.uuid4().hex[:12]}"
    )


    result = execution_loop.run_test_plan(
        plan,
        workspace_root,
    )


    if "error" in result:
        return {
            "status": "error",
            "detail": result["error"],
            "exit_code": None,
            "stdout": "",
            "stderr": "",
        }


    return {
        "status": (
            "passed"
            if result.get("success")
            else "failed"
        ),
        "exit_code": result.get("exit_code"),
        "stdout": result.get("stdout", ""),
        "stderr": result.get("stderr", ""),
    }