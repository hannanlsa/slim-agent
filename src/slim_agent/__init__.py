"""SLIM-Agent: Self-Learning Index Memory for AI agents."""

__version__ = "0.1.7"

# Convenience re-exports so users can write `from slim_agent import PointerStore`
# instead of the longer `from slim_agent.pointer_memory.store import PointerStore`.
# Sub-module paths still work and are the canonical import paths.

from slim_agent.pointer_memory.store import PointerStore
from slim_agent.pointer_memory.models import PointerEntry
from slim_agent.skill_manager.manager import SkillManager
from slim_agent.skill_manager.models import SkillEntry, SkillStatus
from slim_agent.reflection_pool.pool import ReflectionPool
from slim_agent.reflection_pool.models import ReflectionEntry
from slim_agent.slim_reducer.reducer import SlimReducer
from slim_agent.slim_reducer.models import MergeSuggestion, RedundancyReport
from slim_agent.url_fetcher.fetcher import fetch_content, fetch_with_fallback
from slim_agent.url_fetcher.health import check_url, batch_check

__all__ = [
    "__version__",
    # Pointer memory
    "PointerStore",
    "PointerEntry",
    # Skill manager
    "SkillManager",
    "SkillEntry",
    "SkillStatus",
    # Reflection pool
    "ReflectionPool",
    "ReflectionEntry",
    # Slim reducer
    "SlimReducer",
    "MergeSuggestion",
    "RedundancyReport",
    # URL fetcher
    "fetch_content",
    "fetch_with_fallback",
    "check_url",
    "batch_check",
]
