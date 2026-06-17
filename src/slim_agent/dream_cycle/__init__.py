"""Dream Cycle — periodic memory consolidation (3-phase).

Inspired by GBrain's Dream Cycle (8+ stages). We simplify to 3 phases
suitable for flat-file memory:

Phase 1: Daily notes deduplication — remove duplicate entries
Phase 2: Summarize to long-term memory — compress daily notes into MEMORY.md
Phase 3: Stale/broken-link check — verify URLs and flag outdated entries

Design pattern borrowed (no code copied):
- GBrain: "periodic memory consolidation" — scheduled cleanup + summarization
- GBrain: "dream cycle" concept (simplified from 8+ stages to 3)

Usage:
    from slim_agent.dream_cycle import run_dream_cycle, phase_dedup, phase_summarize, phase_stale_check

    # Run all 3 phases
    report = run_dream_cycle(db_path="slim_agent.db")

    # Run individual phase
    dedup_report = phase_dedup(db_path="slim_agent.db")
"""
from slim_agent.dream_cycle.cycle import (
    run_dream_cycle,
    phase_dedup,
    phase_summarize,
    phase_stale_check,
    DreamCycleReport,
)

__all__ = [
    "run_dream_cycle",
    "phase_dedup",
    "phase_summarize",
    "phase_stale_check",
    "DreamCycleReport",
]
