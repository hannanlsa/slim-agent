"""Conservative redundancy scanner — suggests merges, never auto-modifies."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from slim_agent.skill_manager.manager import SkillManager
from slim_agent.skill_manager.models import SkillEntry, SkillStatus
from slim_agent.slim_reducer.models import MergeSuggestion, RedundancyReport


# Minimum Jaccard-like overlap score to suggest a merge (0.0–1.0)
_DEFAULT_THRESHOLD = 0.3


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _summary_similarity(a: str, b: str) -> float:
    """Simple word-overlap similarity on normalised tokens."""
    tokens_a = set(a.lower().split())
    tokens_b = set(b.lower().split())
    return _jaccard(tokens_a, tokens_b)


class SlimReducer:
    """Scan active skills for redundancy and produce merge suggestions."""

    def __init__(self, skill_manager: SkillManager, threshold: float = _DEFAULT_THRESHOLD) -> None:
        self.sm = skill_manager
        self.threshold = threshold
        # Summary-only overlap requires stronger signal than tag overlap
        self.summary_threshold = threshold * 5 / 3

    def scan_skills(self) -> RedundancyReport:
        """Scan all ACTIVE skills for tag/summary overlap and return a RedundancyReport.

        This method is CONSERVATIVE: it only suggests merges. It never modifies
        any skill or database state. Human or AI must approve any action.
        """
        active = self.sm.list_by_status(SkillStatus.ACTIVE)
        report = RedundancyReport(active_skill_count=len(active))

        if len(active) < 2:
            return report

        # Group by tags for fast lookup
        tag_map: dict[str, list[SkillEntry]] = defaultdict(list)
        for s in active:
            for tag in s.tags:
                tag_map[tag].append(s)

        checked: set[tuple[int, int]] = set()
        suggestions: list[MergeSuggestion] = []

        for i, skill in enumerate(active):
            for other in active[i + 1 :]:
                pair = tuple(sorted([skill.id, other.id]))  # type: ignore
                if pair in checked:
                    continue
                checked.add(pair)

                # Tag overlap
                tags_a = set(skill.tags)
                tags_b = set(other.tags)
                tag_score = _jaccard(tags_a, tags_b)
                shared_tags = sorted(tags_a & tags_b)

                # Summary overlap
                summary_score = _summary_similarity(skill.summary, other.summary)

                # Tag and summary use independent thresholds
                overlap_score = max(tag_score, summary_score)

                if tag_score < self.threshold and summary_score < self.summary_threshold:
                    continue

                suggestions.append(
                    MergeSuggestion(
                        skill_ids=[skill.id, other.id],  # type: ignore
                        skill_names=[skill.name, other.name],
                        shared_tags=shared_tags,
                        overlap_score=round(overlap_score, 3),
                        reason=(
                            f"Tag overlap: {len(shared_tags)} shared tags "
                            f"(score={tag_score:.2f}), "
                            f"summary similarity: {summary_score:.2f}"
                        ),
                    )
                )

        report.suggestions = suggestions
        return report