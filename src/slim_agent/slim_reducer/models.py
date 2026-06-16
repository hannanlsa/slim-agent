"""Data models for slim reducer."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class MergeSuggestion:
    """A suggestion to merge two or more overlapping skills."""

    skill_ids: list[int]
    skill_names: list[str]
    shared_tags: list[str]
    overlap_score: float
    reason: str
    severity: str = "info"  # 'ok' | 'info' | 'warning' | 'critical'


@dataclass
class RedundancyReport:
    """Report of all detected skill redundancies."""

    suggestions: list[MergeSuggestion] = field(default_factory=list)
    scanned_at: datetime = field(default_factory=lambda: datetime.now())
    active_skill_count: int = 0

    nudge: str = ""  # LoopDetector 注入的循环提示

    @property
    def has_overlaps(self) -> bool:
        return len(self.suggestions) > 0