"""Eval Framework — lightweight evaluation scenarios for memory quality.

Inspired by GBrain's eval framework: define key evaluation scenarios and
run them periodically to measure memory quality.

5-10 key eval scenarios:
1. Answer accuracy — does memory provide correct answers?
2. Recall rate — can memory find relevant entries?
3. Hallucination detection — does memory flag unknowns?
4. Dedup quality — does slim_reducer find real overlaps?
5. Stale detection — does dream_cycle flag dead URLs?
6. Gap analysis — does gap_analysis detect knowledge gaps?
7. Retrieval reflex — does reflex extract relevant entities?

Design pattern borrowed (no code copied):
- GBrain: "lightweight eval scenarios + periodic run"
- GBrain: structured eval output with pass/fail metrics

Usage:
    from slim_agent.eval_framework import run_evals, EvalResult

    # Run all eval scenarios
    results = run_evals(db_path="slim_agent.db")

    # Print report
    for r in results:
        print(f"{r.scenario}: {r.status} ({r.score:.1%})")
"""
from slim_agent.eval_framework.evaluator import (
    run_evals,
    EvalResult,
    EvalReport,
)

__all__ = ["run_evals", "EvalResult", "EvalReport"]
