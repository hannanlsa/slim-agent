"""Gap Analysis — explicit annotation of memory gaps.

Inspired by GBrain's Gap Analysis: when retrieval results are insufficient,
the agent explicitly marks what it doesn't know with [MEMORY GAP: ...].

This makes knowledge gaps visible and actionable, rather than silently
guessing or hallucinating.

Design pattern borrowed (no code copied):
- GBrain: "明确告知不知道什么" — transparent gap disclosure
- GBrain: confidence scoring for retrieved facts

Usage:
    from slim_agent.gap_analysis import analyze_gaps, mark_gap, format_gap_report

    # Analyze: check if search results cover the question
    gaps = analyze_gaps("What is SimHash?", hits=[])

    # Mark: create a [MEMORY GAP] annotation
    annotation = mark_gap("SimHash implementation details")

    # Format: produce a structured gap report
    report = format_gap_report(gaps)
"""
from slim_agent.gap_analysis.analyzer import (
    analyze_gaps,
    mark_gap,
    format_gap_report,
    GapAnnotation,
)

__all__ = ["analyze_gaps", "mark_gap", "format_gap_report", "GapAnnotation"]
