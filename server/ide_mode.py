"""
Mode 2: IDE Mode.

Backend endpoints a future IDE integration (VS Code extension or
otherwise) will call. This is ONLY the backend contract — no extension
is built here, per the instruction to hold off on that.

Reuses the same CodeAnalysisAgent as Mode 1 (server/agent_interface.py)
rather than duplicating logic — same underlying operations (analyze/
explain/suggest_fix/rewrite), just reshaped around "current file +
project context" instead of a bare code string, and composed into
file-scoped responses that make sense for an editor to render inline.

Design choices worth being explicit about:
  - Mode toggling (Suggest/Assistant/Autonomous, on/off) is NOT tracked
    as server-side state. The IDE extension owns that UI state and
    calls whichever endpoint matches its current mode — keeps the
    backend stateless, no per-user session tracking needed for what's
    really a client-side preference.
  - Autonomous Mode has no endpoint here (matches the original spec
    explicitly calling it out as future work) — nothing in this file
    applies a change without the developer approving it first. /rewrite
    and /debug both return a suggested rewrite; applying it is the
    IDE's job, after the developer looks at a diff.
  - Analysis uses the file PLUS project context (more context = better
    diagnosis), but any returned rewritten_code is generated from the
    raw file content ONLY — never the context-augmented string — so
    it's a clean, directly-usable replacement for the file, not
    contaminated with the context text that was appended for analysis.

Endpoints:
    POST /api/ide/suggestions  -> Suggest Mode: read-only bug/issue detection
    POST /api/ide/rewrite       -> Assistant Mode: suggested fix + patch, for approval
    POST /api/ide/debug          -> full debugging flow for the current file
"""

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from providers.base_provider import ProviderError
from server.dependencies import code_analysis_agent

router = APIRouter(prefix="/api/ide", tags=["ide-mode"])


def _call_or_502(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except ProviderError as e:
        raise HTTPException(status_code=502, detail=f"Provider error: {e}")


class ProjectContext(BaseModel):
    other_files: Optional[dict] = None  # {"path/to/file.py": "file content", ...}


class IDERequest(BaseModel):
    file_path: str
    file_content: str
    language: Optional[str] = None
    project_context: Optional[ProjectContext] = None


class IDEDebugRequest(IDERequest):
    error_message: Optional[str] = None


def _combine_with_context(file_path: str, file_content: str, project_context: Optional[ProjectContext]) -> str:
    parts = [f"# File being analyzed: {file_path}", "", file_content]
    if project_context and project_context.other_files:
        parts.append("")
        parts.append("# Additional project context (other relevant files, for reference only):")
        for path, content in project_context.other_files.items():
            parts.append(f"\n## {path}\n{content}")
    return "\n".join(parts)


@router.post("/suggestions")
def suggestions(payload: IDERequest):
    """Suggest Mode: detect possible bugs, explain issues, recommend
    improvements. Read-only — never modifies the file."""
    combined = _combine_with_context(payload.file_path, payload.file_content, payload.project_context)
    return _call_or_502(code_analysis_agent.analyze, combined, payload.language)

@router.post("/rewrite")
def rewrite(payload: IDERequest):
    """Assistant Mode: suggest a fix and generate the rewritten code as
    a patch for the developer to review — this endpoint never applies
    anything; the IDE shows a diff and the developer approves it."""

    combined = _combine_with_context(
        payload.file_path,
        payload.file_content,
        payload.project_context
    )

    analysis = _call_or_502(
        code_analysis_agent.analyze,
        combined,
        payload.language
    )

    if not analysis.get("issues_found"):
        return {
            "suggested_fix": "",
            "rewritten_code": "",
            "explanation": "No issues found — nothing to rewrite."
        }

    fix = _call_or_502(
        code_analysis_agent.suggest_fix,
        combined,
        analysis.get("explanation", ""),
        payload.language
    )

    rewritten = _call_or_502(
        code_analysis_agent.rewrite,
        payload.file_content,
        fix.get("suggested_fix", ""),
        payload.language
    )

    return {
        "suggested_fix": fix.get("suggested_fix", ""),
        "rewritten_code": rewritten.get("rewritten_code", ""),
        "explanation": rewritten.get("explanation", ""),
    }

@router.post("/debug")
def debug(payload: IDEDebugRequest):
    """Full debugging flow for the current file. If error_message is
    given, starts from explain_error (more targeted, e.g. a stack trace
    the IDE captured); otherwise starts from a general analyze_code
    pass. Returns the same structured contract as Mode 1's /full."""
    combined = _combine_with_context(payload.file_path, payload.file_content, payload.project_context)

    if payload.error_message:
        explanation_result = _call_or_502(code_analysis_agent.explain, combined, payload.error_message, payload.language)
        issues = [payload.error_message]
        severity = explanation_result.get("severity", "unknown")
        explanation = explanation_result.get("explanation", "")
    else:
        analysis = _call_or_502(code_analysis_agent.analyze, combined, payload.language)
        issues = analysis.get("issues_found", [])
        severity = analysis.get("severity", "none")
        explanation = analysis.get("explanation", "")

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

    fix = _call_or_502(code_analysis_agent.suggest_fix, combined, explanation, payload.language)
    # Same discipline as /rewrite: rewrite the raw file, not the context blob.
    rewritten = _call_or_502(code_analysis_agent.rewrite, payload.file_content, fix.get("suggested_fix", ""), payload.language)

    return {
        "issues_found": issues,
        "severity": severity,
        "explanation": explanation,
        "suggested_fix": fix.get("suggested_fix", ""),
        "rewritten_code": rewritten.get("rewritten_code", ""),
        "tests_generated": [],
        "verification_status": "not_run",
    }
