#!/usr/bin/env python3
"""
cycle.py — P1.3 模拟人脑提升: Dream Cycle 轻量版 (3 阶段)

核心功能：
1. phase_dedup(db_path) — 检测并标记重复指针条目
2. phase_summarize(db_path) — 压缩 reflection pool 条目为摘要
3. phase_stale_check(db_path) — 检查过期/断链 URL
4. run_dream_cycle(db_path) — 依次执行 3 阶段

设计借鉴：GBrain 的 Dream Cycle（8+阶段 → 简化为 3 阶段）
实现方式：PointerStore 去重 + ReflectionPool 摘要 + URLFetcher 健康检查

ponytail: L2 stdlib-ok | 已知限制：reflection 摘要只取前80字符 | 升级：加 LLM summarization
"""
from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from slim_agent.pointer_memory.store import PointerStore
from slim_agent.reflection_pool.pool import ReflectionPool
from slim_agent.url_fetcher.health import batch_check


@dataclasses.dataclass
class PhaseResult:
    """单个 Dream Cycle 阶段的结果"""
    phase: str
    items_checked: int = 0
    items_flagged: int = 0
    details: list[str] = dataclasses.field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "items_checked": self.items_checked,
            "items_flagged": self.items_flagged,
            "details": self.details,
        }


@dataclasses.dataclass
class DreamCycleReport:
    """完整的 Dream Cycle 执行报告"""
    timestamp: str = ""
    phases: list[PhaseResult] = dataclasses.field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "phases": [p.to_dict() for p in self.phases],
        }

    def summary(self) -> str:
        lines = [f"[Dream Cycle Report — {self.timestamp}]", ""]
        for p in self.phases:
            lines.append(f"Phase {p.phase}: checked {p.items_checked}, flagged {p.items_flagged}")
            for d in p.details[:5]:
                lines.append(f"  • {d}")
            if len(p.details) > 5:
                lines.append(f"  ... and {len(p.details) - 5} more")
        return "\n".join(lines)


def phase_dedup(db_path: str = "slim_agent.db") -> PhaseResult:
    """
    Phase 1: Daily notes deduplication.

    Detects pointer entries with identical or near-identical summaries
    (exact match on summary text). Flags duplicates for human review.

    Note: this phase is advisory only — it does NOT auto-delete duplicates.
    That requires human or AI approval (Copilot Not Pilot).
    """
    store = PointerStore(db_path)
    entries = store.list_all()

    # Group by normalized summary (lowercase, stripped)
    summary_map: dict[str, list[int]] = {}
    for e in entries:
        normalized = e.summary.lower().strip()
        summary_map.setdefault(normalized, []).append(e.id)

    # Find duplicates (entries with same normalized summary)
    flagged: list[str] = []
    for norm, ids in summary_map.items():
        if len(ids) > 1:
            flagged.append(f"Duplicate summary '{norm[:40]}...' IDs: {ids}")

    store.close()

    return PhaseResult(
        phase="dedup",
        items_checked=len(entries),
        items_flagged=len(flagged),
        details=flagged,
    )


def phase_summarize(db_path: str = "slim_agent.db") -> PhaseResult:
    """
    Phase 2: Summarize to long-term memory.

    Scans the reflection pool and identifies entries that could be
    compressed (long lesson_learned or context strings). Flags them
    for summarization.

    Note: actual summarization requires LLM or human intervention.
    This phase only identifies candidates.
    """
    pool = ReflectionPool(db_path)
    entries = pool.list_all()

    # Flag entries with long content that could be compressed
    LONG_THRESHOLD = 200  # characters

    flagged: list[str] = []
    for e in entries:
        combined_len = len(e.lesson_learned) + len(e.context)
        if combined_len > LONG_THRESHOLD:
            # ponytail: 截断摘要只取前80字符 — 简单但实用
            flagged.append(
                f"Reflection #{e.id}: {combined_len} chars (lesson: '{e.lesson_learned[:40]}...')"
            )

    pool.close()

    return PhaseResult(
        phase="summarize",
        items_checked=len(entries),
        items_flagged=len(flagged),
        details=flagged,
    )


def phase_stale_check(db_path: str = "slim_agent.db", timeout: float = 5.0) -> PhaseResult:
    """
    Phase 3: Stale/broken-link check.

    Verifies that all pointer URLs are still alive. Flags dead URLs
    for remediation (fallback URL addition or entry deletion).

    Uses url_fetcher.health.batch_check for actual HTTP verification.
    """
    store = PointerStore(db_path)
    entries = store.list_all()

    urls = list({e.primary_url for e in entries})
    if not urls:
        store.close()
        return PhaseResult(phase="stale_check", items_checked=0, items_flagged=0)

    report = batch_check(urls, timeout=timeout)

    # Flag dead URLs
    flagged: list[str] = []
    dead_urls = set()
    for r in report.results:
        if not r.alive:
            flagged.append(f"Dead URL: {r.url[:60]} (status={r.status_code}, error={r.error})")
            dead_urls.add(r.url)

    # Find which entries reference dead URLs
    for e in entries:
        if e.primary_url in dead_urls:
            flagged.append(f"  → Pointer #{e.id} uses dead URL: '{e.summary[:40]}...'")

    store.close()

    return PhaseResult(
        phase="stale_check",
        items_checked=len(urls),
        items_flagged=len(flagged),
        details=flagged,
    )


def run_dream_cycle(
    db_path: str = "slim_agent.db",
    timeout: float = 5.0,
) -> DreamCycleReport:
    """
    Execute all 3 Dream Cycle phases in sequence.

    Returns a DreamCycleReport with results from each phase.
    """
    now = datetime.now(timezone.utc).isoformat()

    p1 = phase_dedup(db_path)
    p2 = phase_summarize(db_path)
    p3 = phase_stale_check(db_path, timeout=timeout)

    return DreamCycleReport(
        timestamp=now,
        phases=[p1, p2, p3],
    )


# ─── self-test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import tempfile

    # Use a temp DB for testing
    db = tempfile.mktemp(suffix=".db")

    # Initialize tables
    ps = PointerStore(db)
    sm_store = PointerStore(db)
    rp = ReflectionPool(db)
    from slim_agent.skill_manager.manager import SkillManager
    sm = SkillManager(db)
    ps.init_db()
    sm.init_db()
    rp.init_db()

    # Add some pointers (including duplicates)
    ps.add_pointer(summary="SimHash fingerprint tutorial", primary_url="https://a.com", tags=["simhash"])
    ps.add_pointer(summary="SimHash fingerprint tutorial", primary_url="https://b.com", tags=["simhash"])  # duplicate
    ps.add_pointer(summary="BM25 keyword matching", primary_url="https://c.com", tags=["bm25"])

    # Add reflections (including a long one)
    rp.add(error_type="TimeoutError", error_message="request timed out", context="short context", lesson_learned="set timeout")
    rp.add(error_type="RuntimeError", error_message="division by zero",
           context="very long context that exceeds the threshold " * 10,
           lesson_learned="check divisor before operation and also ensure that the denominator is non-zero before performing any arithmetic calculation that could result in a division error")

    ps.close()
    sm.close()
    rp.close()

    # Phase 1: dedup
    p1 = phase_dedup(db)
    print(f"Phase dedup: checked {p1.items_checked}, flagged {p1.items_flagged}")
    assert p1.items_checked == 3, "should check 3 pointers"
    assert p1.items_flagged == 1, "should flag 1 duplicate group"

    # Phase 2: summarize
    p2 = phase_summarize(db)
    print(f"Phase summarize: checked {p2.items_checked}, flagged {p2.items_flagged}")
    assert p2.items_checked == 2, "should check 2 reflections"
    # The long reflection should be flagged

    # Phase 3: stale check (skip actual HTTP in self-test)
    p3 = phase_stale_check(db, timeout=0.001)
    print(f"Phase stale_check: checked {p3.items_checked}")
    # URLs are fake, they'll be dead — that's expected

    # Full cycle
    report = run_dream_cycle(db, timeout=0.001)
    print(f"\n{report.summary()}")
    assert len(report.phases) == 3, "should have 3 phases"

    # Cleanup
    import os
    os.unlink(db)

    print("\n✅ All self-tests passed")
