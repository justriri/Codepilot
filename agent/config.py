"""
Configuration layer.

Centralizes every environment-driven setting so nothing is hardcoded
elsewhere in the codebase. Loads from a .env file (via python-dotenv)
if present, falling back to real environment variables.

As of the multi-provider architecture: no single API key is required
here anymore. Only the key for whichever provider DEFAULT_MODEL selects
is required, and that check happens in providers/router.py at the point
a provider is actually constructed — not unconditionally here, since a
DeepSeek-only user shouldn't be forced to set an Anthropic key.
"""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass
class AgentConfig:
    workspace_root: str
    max_iterations: int
    command_timeout_s: int

    # --- Model provider settings ---
    default_model_provider: str

    anthropic_api_key: str
    anthropic_model: str

    deepseek_api_key: str
    deepseek_model: str

    openai_api_key: str
    openai_model: str

    local_model_name: str
    local_model_base_url: str

    # --- Sandbox settings ---
    docker_image: str
    sandbox_mem_limit: str
    sandbox_nano_cpus: int
    sandbox_pids_limit: int
    sandbox_ttl_s: int

    # --- Debugging loop settings ---
    max_repair_attempts: int
    debug_agent_max_iterations: int

    # --- Memory settings ---
    memory_db_path: str



def load_config() -> AgentConfig:
    return AgentConfig(

        # --- General agent settings ---
        workspace_root=os.environ.get(
            "WORKSPACE_ROOT",
            "./workspace"
        ),

        max_iterations=int(
            os.environ.get(
                "MAX_ITERATIONS",
                "35"
            )
        ),

        command_timeout_s=int(
            os.environ.get(
                "COMMAND_TIMEOUT_S",
                "30"
            )
        ),


        # --- Model provider settings ---

        default_model_provider=os.environ.get(
            "DEFAULT_MODEL",
            "deepseek"
        ),


        anthropic_api_key=os.environ.get(
            "ANTHROPIC_API_KEY",
            ""
        ),

        # Kept AGENT_MODEL fallback for older .env files
        anthropic_model=os.environ.get(
            "ANTHROPIC_MODEL",
            os.environ.get(
                "AGENT_MODEL",
                "claude-sonnet-4-5"
            )
        ),


        deepseek_api_key=os.environ.get(
            "DEEPSEEK_API_KEY",
            ""
        ),

        deepseek_model=os.environ.get(
            "DEEPSEEK_MODEL",
            "deepseek-v4-pro"
        ),


        openai_api_key=os.environ.get(
            "OPENAI_API_KEY",
            ""
        ),

        openai_model=os.environ.get(
            "OPENAI_MODEL",
            "gpt-5"
        ),


        local_model_name=os.environ.get(
            "LOCAL_MODEL_NAME",
            ""
        ),

        local_model_base_url=os.environ.get(
            "LOCAL_MODEL_BASE_URL",
            "http://localhost:11434/v1"
        ),


        # --- Sandbox settings ---

        docker_image=os.environ.get(
            "DOCKER_IMAGE",
            "agent-sandbox:latest"
        ),

        sandbox_mem_limit=os.environ.get(
            "SANDBOX_MEM_LIMIT",
            "512m"
        ),

        # 1_000_000_000 nano_cpus == 1 full CPU core
        sandbox_nano_cpus=int(
            os.environ.get(
                "SANDBOX_NANO_CPUS",
                "1000000000"
            )
        ),

        sandbox_pids_limit=int(
            os.environ.get(
                "SANDBOX_PIDS_LIMIT",
                "128"
            )
        ),

        # Hard wall-clock cap per sandbox
        sandbox_ttl_s=int(
            os.environ.get(
                "SANDBOX_TTL_S",
                "600"
            )
        ),


        # --- Debugging loop settings ---

        # Maximum fix -> test -> retry cycles
        max_repair_attempts=int(
            os.environ.get(
                "MAX_REPAIR_ATTEMPTS",
                "3"
            )
        ),

        # Maximum internal debugging-agent reasoning/tool cycles
        debug_agent_max_iterations=int(
            os.environ.get(
                "DEBUG_AGENT_MAX_ITERATIONS",
                "6"
            )
        ),


        # --- Memory settings ---

        memory_db_path=os.environ.get(
            "MEMORY_DB_PATH",
            "./agent_memory.db"
        ),
    )