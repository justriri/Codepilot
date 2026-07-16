"""
Shared dependencies for stateless API routers.

Provider, agents, execution loop, and memory are initialized lazily.
Nothing expensive happens during import time.

This prevents startup/import crashes when:
- API keys are missing
- provider configuration is invalid
- filesystem-backed memory initialization fails

Real initialization happens only when a route actually needs the dependency.
"""

from agent.config import load_config
from agent.agents.code_analysis_agent import CodeAnalysisAgent
from agent.agents.execution_loop import ExecutionLoop
from agent.memory.memory_manager import MemoryManager
from providers.router import get_provider


_code_analysis_agent = None
_execution_loop = None
_memory_manager = None


def _ensure_initialized():

    global _code_analysis_agent, _execution_loop, _memory_manager

    config = None

    if (
        _code_analysis_agent is None
        or _execution_loop is None
        or _memory_manager is None
    ):
        config = load_config()


    if _code_analysis_agent is None:

        provider = get_provider(config)

        _code_analysis_agent = CodeAnalysisAgent(
            provider
        )


    if _execution_loop is None:

        _execution_loop = ExecutionLoop(
            _code_analysis_agent,
            max_repair_attempts=config.max_repair_attempts,
        )


    if _memory_manager is None:

        from agent.memory.long_term_memory import LongTermMemory

        _memory_manager = MemoryManager(
            long_term_memory=LongTermMemory(
                db_path=config.memory_db_path
            )
        )



class _LazyProxy:
    """
    Delays object creation until the dependency is actually accessed.

    Existing routes can continue using:

        execution_loop.run(...)
        code_analysis_agent.analyze(...)
        memory_manager.search(...)

    without knowing initialization is lazy.
    """


    def __init__(self, getter):

        self._getter = getter



    def __getattr__(self, name):

        return getattr(
            self._getter(),
            name,
        )



def _get_code_analysis_agent():

    _ensure_initialized()

    return _code_analysis_agent



def _get_execution_loop():

    _ensure_initialized()

    return _execution_loop



def _get_memory_manager():

    _ensure_initialized()

    return _memory_manager



code_analysis_agent = _LazyProxy(
    _get_code_analysis_agent
)


execution_loop = _LazyProxy(
    _get_execution_loop
)


memory_manager = _LazyProxy(
    _get_memory_manager
)