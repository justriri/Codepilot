"""
CLI entry point.

Wires together config, workspace, model provider, tool executor, and the
agent controller, then runs a single request end-to-end.

The provider is selected via DEFAULT_MODEL in .env (anthropic, deepseek,
openai, or local) — this file never hardcodes which one, see
providers/router.py.

Usage:
    python main.py "Build me a simple landing page."

Or, with no arguments, it will prompt you interactively.
"""

import sys

from agent.config import load_config
from agent.workspace import Workspace
from agent.sandbox.manager import SandboxManager
from agent.agents.debugging_agent import DebuggingAgent
from agent.agents.repair_loop import TestRepairLoop
from agent.tools.executor import ToolExecutor
from agent.controller import AgentController
from providers.router import get_provider


def main():
    config = load_config()

    workspace = Workspace(config.workspace_root)
    provider = get_provider(config)
    sandbox = SandboxManager(workspace.root, config)

    # Construction order matters here: DebuggingAgent only needs
    # (provider, workspace) — not the full ToolExecutor — specifically so
    # this doesn't become circular (ToolExecutor needs the repair loop,
    # the repair loop needs the debugging agent).
    debugging_agent = DebuggingAgent(provider, workspace, config.debug_agent_max_iterations)
    repair_loop = TestRepairLoop(sandbox, debugging_agent, config.max_repair_attempts)

    executor = ToolExecutor(workspace, sandbox, config.command_timeout_s, repair_loop=repair_loop)
    controller = AgentController(config, provider, executor, sandbox)

    if len(sys.argv) > 1:
        request = " ".join(sys.argv[1:])
    else:
        request = input("What would you like the agent to build?\n> ")

    print(f"\n=== Starting agent ===\nProvider: {provider.name}\nRequest: {request}\nWorkspace: {workspace.root}\n")

    try:
        summary = controller.run(request)
    except KeyboardInterrupt:
        # controller.run()'s own finally block already destroys the sandbox
        # before this exception propagates up, so no extra cleanup needed here.
        print("\n\nInterrupted — sandbox has been cleaned up.")
        return

    print("\n=== Agent finished ===\n")
    print(summary)
    print(f"\nProject files are in: {workspace.root}")


if __name__ == "__main__":
    main()
