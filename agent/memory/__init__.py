"""
Three-layer agent memory system.

- working_memory: ephemeral, one request's context (formalizes what
  already existed implicitly as local variables)
- session_memory: in-process, scoped to a session_id, forgotten on
  server restart
- long_term_memory: SQLite-backed, persists across restarts

memory_manager.MemoryManager is the only entry point other code should
use — it composes all three layers so callers never touch a specific
layer's storage directly.
"""

from agent.memory.memory_manager import MemoryManager

__all__ = ["MemoryManager"]