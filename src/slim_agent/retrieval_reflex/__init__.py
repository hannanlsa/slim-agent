"""Retrieval Reflex — automatic entity extraction + context injection.

Inspired by GBrain's Retrieval Reflex: when an agent encounters a salient entity
(e.g. a person, project, or concept name), it automatically searches its memory
and injects relevant context into the current conversation.

Design patterns borrowed (no code copied):
- GBrain: "scan context → extract entity → memory_search → inject"
- GBrain: regex-based entity extraction (lightweight, no NLP dependency)

Usage:
    from slim_agent.retrieval_reflex import extract_entities, reflex_search, inject_context

    # 1. Extract salient entities from text
    entities = extract_entities("OpenHuman uses SimHash for CJK text")

    # 2. Search memory for each entity
    hits = reflex_search(entities, store=PointerStore("slim_agent.db"))

    # 3. Build injected context block
    context = inject_context(hits)
"""
from slim_agent.retrieval_reflex.reflex import (
    extract_entities,
    reflex_search,
    inject_context,
)

__all__ = ["extract_entities", "reflex_search", "inject_context"]
