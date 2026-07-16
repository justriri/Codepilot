"""
Debugging Agent.

A dedicated, narrowly-scoped LLM role invoked only when run_test_flow
reports a failure. Deliberately separate from the main coding agent
(AgentController) for a specific reason: this role's job is root-cause
analysis and a targeted repair, not general project construction, so it
gets a different system prompt and a much smaller tool set — just the
file tools. It never touches the sandbox lifecycle directly (no
create_sandbox / install_dependencies / start_application / etc).

Runs on the HOST, not inside the sandbox container:
  - It needs API credentials for whichever provider is configured, which
    should never be exposed inside the container the agent's own
    generated code executes in.
  - It reuses agent/tools/filesystem.py directly (not the full
    ToolExecutor) to avoid a circular construction dependency: the
    ToolExecutor needs a repair loop, which needs this agent — if this
    agent also needed the ToolExecutor, nothing could be constructed
    first. filesystem.py's functions only need a Workspace, which this
    agent already has, so going through them directly is both simpler
    and sufficient.

Failure evidence is passed as a multimodal message: structured text
(failed steps, console errors, app log tail) PLUS the actual screenshot
images for any failed step that has one, using the normalized ImageBlock
type — so the model can literally see the broken page, not just read
selector names, REGARDLESS of which provider is configured. Each
provider translates ImageBlock into its own wire format (see
providers/anthropic_provider.py and providers/_openai_compatible.py).
"""

import base64
import json
import os

from agent.tools import filesystem
from agent.tools.definitions import TOOL_DEFINITIONS
from agent.workspace import Workspace
from providers.base_provider import BaseProvider, ImageBlock, ProviderError, TextBlock, ToolResult

DEBUGGING_TOOL_NAMES = {"read_file", "list_files", "create_file"}

SYSTEM_PROMPT = """You are a debugging specialist. You are given evidence that an
application's automated browser test failed: which steps failed, error
details, console/application logs, and screenshots at the moment of
failure. Your job is NOT to build new features — it is to find the
root cause of the failure and apply the smallest correct fix.

Follow this process:
1. Review the failure evidence provided (failed steps, error details,
   logs, screenshots).
2. Use list_files and read_file to inspect the relevant project files.
   Do not guess at file contents — read them.
3. Identify the specific file and the specific problem causing the
   failure.
4. Apply a fix using create_file (which overwrites the file with the
   full corrected content).
5. Reply with a brief plain-text explanation of the root cause and
   what you changed. Do not call any more tools once you're confident
   the fix is applied — stop and explain.

Rules:
- Make the smallest change that fixes the actual root cause. Do not
  rewrite unrelated parts of the file.
- If you cannot determine a confident fix from the evidence, say so
  plainly in your final explanation rather than guessing destructively.
"""


class DebuggingAgent:
    def __init__(self, provider: BaseProvider, workspace: Workspace, max_iterations: int = 6):
        self.provider = provider
        self.workspace = workspace
        self.max_iterations = max_iterations
        self.tool_defs = [t for t in TOOL_DEFINITIONS if t["name"] in DEBUGGING_TOOL_NAMES]

    def analyze_and_fix(self, test_result: dict) -> dict:
        """
        Given a failed run_test_flow result, ask the configured provider
        to diagnose and fix the underlying issue. Returns a dict
        describing what was done (success, explanation, actions) for
        logging and reporting.
        """
        messages = [{"role": "user", "content": self._build_prompt_content(test_result)}]
        actions_taken = []

        for _ in range(self.max_iterations):
            try:
                response = self.provider.send(messages, self.tool_defs, SYSTEM_PROMPT)
            except ProviderError as e:
                return {
                    "success": False,
                    "explanation": f"The {self.provider.name} provider returned an error: {e}",
                    "actions": actions_taken,
                }

            messages.append({"role": "assistant", "content": response.content})

            tool_uses = [b for b in response.content if b.type == "tool_use"]

            if not tool_uses:
                explanation = "\n".join(b.text for b in response.content if b.type == "text").strip()
                return {
                    "success": True,
                    "explanation": explanation or "(No explanation provided.)",
                    "actions": actions_taken,
                }

            tool_results = []
            for tool_use in tool_uses:
                result = self._execute_tool(tool_use.name, tool_use.input)
                actions_taken.append({"tool": tool_use.name, "input": tool_use.input, "result": result})
                tool_results.append(ToolResult(tool_call_id=tool_use.id, content=json.dumps(result)))
            messages.append({"role": "tool_results", "content": tool_results})

        return {
            "success": False,
            "explanation": "Debugging agent reached its iteration limit without concluding a fix.",
            "actions": actions_taken,
        }

    def _execute_tool(self, name: str, tool_input: dict) -> dict:
        """Deliberately reuses agent/tools/filesystem.py directly rather
        than the full ToolExecutor — see module docstring for why."""
        try:
            if name == "read_file":
                return filesystem.read_file(self.workspace, tool_input["path"])
            if name == "list_files":
                return filesystem.list_files(self.workspace)
            if name == "create_file":
                return filesystem.create_file(self.workspace, tool_input["path"], tool_input.get("content", ""))
            return {"success": False, "error": f"Unknown tool: {name}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _build_prompt_content(self, test_result: dict) -> list:
        """Builds the multimodal message: structured failure text, plus
        real screenshot images (as normalized ImageBlocks — see module
        docstring) for any failed step that has one."""
        failed_steps = [s for s in test_result.get("steps", []) if not s.get("passed")]

        lines = ["A browser test flow failed. Here is the evidence:", ""]
        lines.append("Failed steps:")
        if failed_steps:
            for s in failed_steps:
                lines.append(
                    f"- Step {s.get('index')} ({s.get('action')} on '{s.get('selector')}'): {s.get('detail')}"
                )
        else:
            lines.append("(No individual step failures recorded — see runner error below, if any.)")
        lines.append("")

        console_errors = test_result.get("console_errors", [])
        if console_errors:
            lines.append("Browser console errors:")
            for e in console_errors:
                lines.append(f"- {e}")
            lines.append("")

        if test_result.get("error"):
            lines.append(f"Test runner error: {test_result['error']}")
            lines.append("")

        app_log_tail = self._read_app_log_tail()
        if app_log_tail:
            lines.append("Application log ('.sandbox/app.log', tail):")
            lines.append(app_log_tail)
            lines.append("")

        lines.append(
            "Use list_files and read_file to inspect the project, find the root "
            "cause, and use create_file to apply a fix."
        )

        content = [TextBlock(text="\n".join(lines))]

        for s in failed_steps:
            image_block = self._load_screenshot_block(s.get("screenshot"))
            if image_block:
                content.append(image_block)
                content.append(
                    TextBlock(text=f"(Screenshot above is from failed step {s.get('index')}: {s.get('action')})")
                )

        return content

    def _read_app_log_tail(self, max_chars: int = 2000):
        try:
            full_path = self.workspace.resolve(".sandbox/app.log")
        except ValueError:
            return None
        if not os.path.isfile(full_path):
            return None
        try:
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                return f.read()[-max_chars:]
        except Exception:
            return None

    def _load_screenshot_block(self, screenshot_rel_path):
        if not screenshot_rel_path:
            return None
        try:
            full_path = self.workspace.resolve(screenshot_rel_path)
        except ValueError:
            return None
        if not os.path.isfile(full_path):
            return None  # a missing/corrupt screenshot shouldn't block debugging
        try:
            with open(full_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
            return ImageBlock(data=b64, media_type="image/png")
        except Exception:
            return None
