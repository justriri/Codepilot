"""
Test Plan Builder.

Turns generated test-case strings (from BaseProvider.generate_tests())
into something concretely executable inside a Docker sandbox.

Design choice: combine the solution code and generated tests into ONE
file, run directly with the plain interpreter (python/node) — not a
test framework (pytest/jest). This deliberately avoids two fragile
things: (a) guessing whether the LLM's generated tests correctly
`import` from a separately-named solution file (unpredictable across
generations), and (b) needing install_dependencies to pull in a test
framework before every verification run. generate_tests()'s existing
prompt already asks for "a complete, runnable test case" — concatenating
and running directly honors that framing. An assertion failure or
uncaught exception anywhere in the combined file surfaces as a non-zero
exit code, which SandboxManager.exec_command() already captures.

Explicit per-language mapping, not auto-detection magic — matching the
honesty standard CodeAnalysisAgent.verify() already sets (it requires an
explicit verify_command rather than guessing). An unsupported language
gets a clear error, not a silent wrong guess.
"""

LANGUAGE_RUNNERS = {
    "python": {
        "filename": "solution_with_tests.py",
        "run_command": "python3 solution_with_tests.py",
        "separator": "\n\n# --- Generated tests ---\n\n",
    },
    "javascript": {
        "filename": "solution_with_tests.js",
        "run_command": "node solution_with_tests.js",
        "separator": "\n\n// --- Generated tests ---\n\n",
    },
}


def build_test_plan(code: str, tests_generated: list, language: str) -> dict:
    """
    Returns:
        {"success": True, "files": {filename: content}, "run_command": str}
        or
        {"success": False, "error": str}   # unsupported language
    """
    lang = (language or "").strip().lower()
    if lang not in LANGUAGE_RUNNERS:
        return {
            "success": False,
            "error": f"No test-plan template for language '{language}'. Supported: {list(LANGUAGE_RUNNERS)}",
        }

    spec = LANGUAGE_RUNNERS[lang]
    tests_block = "\n\n".join(t for t in (tests_generated or []) if t and t.strip())

    combined = code.rstrip()
    if tests_block:
        combined += spec["separator"] + tests_block
    combined += "\n"

    return {
        "success": True,
        "files": {spec["filename"]: combined},
        "run_command": spec["run_command"],
    }
