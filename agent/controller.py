"""
Agent controller — the brain of the coding agent.

Handles:
- LLM conversation loop
- Tool execution
- Event streaming for web UI
- Sandbox lifecycle cleanup

Supports:
- CLI mode (main.py)
- Web mode (SessionManager + FastAPI)
"""

import json

from agent.config import AgentConfig
from agent.sandbox.manager import SandboxManager
from agent.tools.definitions import TOOL_DEFINITIONS
from agent.tools.executor import ToolExecutor
from providers.base_provider import BaseProvider, ProviderError, ToolResult


SYSTEM_PROMPT = """
You are an autonomous coding agent that builds, runs, and verifies
projects inside an isolated Docker sandbox.

Workflow:

1. Understand the user's request.
2. Create a sandbox.
3. Create and modify files using available tools.
4. Install dependencies when needed.
5. Start applications when required.
6. Verify functionality using testing tools.
7. Debug failures and retry when possible.
8. Generate verification reports.
9. Clean up sandbox resources.
10. Provide a concise final summary.

Rules:
- Always create a sandbox before using sandbox tools.
- Prefer complete working files.
- Verify applications instead of assuming they work.
- Clean up resources before finishing.
"""


class AgentController:

    def __init__(
        self,
        config: AgentConfig,
        provider: BaseProvider,
        executor: ToolExecutor,
        sandbox: SandboxManager,
    ):
        self.config = config
        self.provider = provider
        self.executor = executor
        self.sandbox = sandbox


    def run(self, user_request: str, on_event=None) -> str:
        """
        Execute one complete agent task.

        on_event:
            Optional callback used by the web interface to stream
            progress events to connected clients.

        CLI mode:
            Prints events normally.

        Web mode:
            Sends events to SessionManager.
        """

        emit = on_event or self._print_event

        messages = [
            {
                "role": "user",
                "content": user_request
            }
        ]

        self._emit_safe(
            emit,
            {
                "type": "session_started",
                "request": user_request,
            }
        )

        try:

            for iteration in range(
                1,
                self.config.max_iterations + 1
            ):

                self._emit_safe(
                    emit,
                    {
                        "type": "iteration_start",
                        "iteration": iteration,
                        "max_iterations": self.config.max_iterations,
                    },
                )


                try:
                    response = self.provider.send(
                        messages,
                        TOOL_DEFINITIONS,
                        SYSTEM_PROMPT,
                    )


                except ProviderError as e:

                    msg = (
                        f"{self.provider.name} provider error: {e}"
                    )

                    self._emit_safe(
                        emit,
                        {
                            "type": "error",
                            "message": msg
                        },
                    )

                    return msg


                except Exception as e:

                    msg = (
                        f"Unexpected provider failure: {e}"
                    )

                    self._emit_safe(
                        emit,
                        {
                            "type": "error",
                            "message": msg
                        },
                    )

                    return msg



                messages.append(
                    {
                        "role": "assistant",
                        "content": response.content,
                    }
                )


                for block in response.content:

                    if (
                        block.type == "text"
                        and block.text.
                        strip()
                    ):
                        self._emit_safe(
                            emit,
                            {
                                "type": "agent_text",
                                "text": block.text.strip(),
                            },
                        )



                tool_calls = [
                    block
                    for block in response.content
                    if block.type == "tool_use"
                ]



                if not tool_calls:

                    final_text = self._extract_final_text(
                        response
                    )

                    self._emit_safe(
                        emit,
                        {
                            "type": "final_summary",
                            "text": final_text,
                        },
                    )

                    return final_text



                tool_results = []


                for tool_call in tool_calls:

                    self._emit_safe(
                        emit,
                        {
                            "type": "tool_call",
                            "name": tool_call.name,
                            "input": tool_call.input,
                        },
                    )


                    try:

                        result = self.executor.execute(
                            tool_call.name,
                            tool_call.input,
                        )

                    except Exception as e:

                        result = {
                            "success": False,
                            "error": str(e),
                        }



                    self._emit_safe(
                        emit,
                        {
                            "type": "tool_result",
                            "name": tool_call.name,
                            "result": result,
                        },
                    )


                    tool_results.append(
                        ToolResult(
                            tool_call_id=tool_call.id,
                            content=json.dumps(result),
                        )
                    )



                messages.append(
                    {
                        "role": "tool_results",
                        "content": tool_results,
                    }
                )



            msg = (
                "Maximum iterations reached before completion."
            )

            self._emit_safe(
                emit,
                {
                    "type": "error",
                    "message": msg,
                },
            )

            return msg



        finally:

            if self.sandbox.is_active:

                self._emit_safe(
                    emit,
                    {
                        "type": "info",
                        "message": (
                            "Cleaning up sandbox..."
                        ),
                    },
                )

                self.sandbox.destroy()



    @staticmethod
    def _emit_safe(callback, event):

        try:
            callback(event)

        except Exception:
            # Never allow UI/event streaming failures
            # to break the agent itself.
            pass



    @staticmethod
    def _print_event(event: dict):

        event_type = event.get("type")


        if event_type == "iteration_start":

            print(
                f"\n--- Iteration "
                f"{event['iteration']}/"
                f"{event['max_iterations']} ---"
            )


        elif event_type == "agent_text":

            print(
                f"[agent] {event['text']}"
            )


        elif event_type == "tool_call":

            print(
                f"[tool call] "
                f"{event['name']} "
                f"{json.dumps(event['input'])[:300]}"
            )


        elif event_type == "tool_result":

            print(
                f"[tool result] "
                f"{json.
                   dumps(event['result'])[:300]}"
            )


        elif event_type == "error":

            print(
                f"[error] {event['message']}"
            )


        elif event_type == "info":

            print(
                f"[controller] {event['message']}"
            )



    @staticmethod
    def _extract_final_text(response) -> str:

        texts = [
            block.text
            for block in response.content
            if block.type == "text"
        ]

        return (
            "\n".join(texts)
            if texts
            else "(Agent finished without summary.)"
        )