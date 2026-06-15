"""Conservative redundancy scanner — suggests merges, never auto-modifies."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from slim_agent.skill_manager.manager import SkillManager
from slim_agent.skill_manager.models import SkillEntry, SkillStatus
from slim_agent.slim_reducer.models import MergeSuggestion, RedundancyReport
from slim_agent.slim_reducer.simhash import simhash, simhash_similarity


# Minimum Jaccard-like overlap score to suggest a merge (0.0–1.0)
_DEFAULT_THRESHOLD = 0.3
# SimHash similarity threshold (above this, two summaries are near-duplicates)
_DEFAULT_SIMHASH_THRESHOLD = 0.65


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _summary_similarity(a: str, b: str) -> float:
    """Word-overlap Jaccard on normalised tokens (English-friendly baseline)."""
    tokens_a = set(a.lower().split())
    tokens_b = set(b.lower().split())
    return _jaccard(tokens_a, tokens_b)


class SlimReducer:
    """Scan active skills for redundancy and produce merge suggestions.

    Three signals, combined:
      1. Tag Jaccard (threshold-controlled)
      2. Summary word Jaccard (CJK-fragile, kept for back-compat)
      3. Summary SimHash similarity (CJK + typo + paraphrase robust)

    Conservative: only suggests, never modifies. Human/AI must approve actions.
    """

    def __init__(
        self,
        skill_manager: SkillManager,
        threshold: float = _DEFAULT_THRESHOLD,
        simhash_threshold: float = _DEFAULT_SIMHASH_THRESHOLD,
    ) -> None:
        self.sm = skill_manager
        self.threshold = threshold
        self.summary_threshold = threshold * 5 / 3
        self.simhash_threshold = simhash_threshold

    def scan_skills(self) -> RedundancyReport:
        """Scan all ACTIVE skills and return a RedundancyReport."""
        active = self.sm.list_by_status(SkillStatus.ACTIVE)
        report = RedundancyReport(active_skill_count=len(active))

        if len(active) < 2:
            return report

        # Pre-compute SimHash fingerprints for all summaries (avoids recomputation per pair)
        fingerprints = {s.id: simhash(s.summary or "") for s in active}  # type: ignore

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

                # Summary word-Jaccard (English baseline)
                summary_score = _summary_similarity(skill.summary, other.summary)

                # Summary SimHash (CJK + paraphrase robust)
                sh_score = simhash_similarity(
                    fingerprints[skill.id],  # type: ignore
                    fingerprints[other.id],  # type: ignore
                )

                # Combined overlap = max of three signals
                overlap_score = max(tag_score, summary_score, sh_score)

                # Trigger on any signal above its threshold
                tag_hit = tag_score >= self.threshold
                summary_hit = summary_score >= self.summary_threshold
                simhash_hit = sh_score >= self.simhash_threshold
                if not (tag_hit or summary_hit or simhash_hit):
                    continue

                # Build a reason listing which signals fired
                signals = []
                if tag_hit:
                    signals.append(f"tag Jaccard={tag_score:.2f}")
                if summary_hit:
                    signals.append(f"word Jaccard={summary_score:.2f}")
                if simhash_hit:
                    signals.append(f"simhash={sh_score:.2f}")

                suggestions.append(
                    MergeSuggestion(
                        skill_ids=[skill.id, other.id],  # type: ignore
                        skill_names=[skill.name, other.name],
                        shared_tags=shared_tags,
                        overlap_score=round(overlap_score, 3),
                        reason=(
                            f"Overlap signals: {', '.join(signals)}. "
                            f"Shared tags: {len(shared_tags)}"
                        ),
                    )
                )

        report.suggestions = suggestions
        return report
