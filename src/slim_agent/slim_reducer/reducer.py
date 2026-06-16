"""Conservative redundancy scanner — suggests merges, never auto-modifies."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from slim_agent.skill_manager.manager import SkillManager
from slim_agent.skill_manager.models import SkillEntry, SkillStatus
from slim_agent.slim_reducer.models import MergeSuggestion, RedundancyReport
from slim_agent.slim_reducer.registry import SignalRegistry, create_default_registry
from slim_agent.slim_reducer.loop_detector import LoopDetector


class SlimReducer:
    """Scan active skills for redundancy and produce merge suggestions.

    Three signals + BM25, combined via RRF (借鉴 Qdrant):
      1. Tag Jaccard (default threshold 0.3)
      2. Summary word Jaccard (default threshold 0.5)
      3. Summary SimHash similarity (default threshold 0.65)
      4. BM25 keyword matching (threshold 0.15, 借鉴 Qdrant lib/bm25/)

    Score fusion: RRF (Reciprocal Rank Fusion, 借鉴 Qdrant)

    Conservative: only suggests, never modifies. Human/AI must approve actions.

    v0.1.7: signals 动态注册/禁用 via SignalRegistry
    v0.1.7: 渐进式循环检测 via LoopDetector
    v0.1.7: 合并建议分级 (info/warning/critical)
    v0.1.8: BM25 keyword matching (借鉴 Qdrant lib/bm25/)
    v0.1.8: RRF score fusion (借鉴 Qdrant RRF)
    """

    def __init__(
        self,
        skill_manager: SkillManager,
        registry: SignalRegistry | None = None,
        loop_detector: LoopDetector | None = None,
    ) -> None:
        self.sm = skill_manager
        self.registry = registry or create_default_registry()
        self.loop_detector = loop_detector or LoopDetector()

    def scan_skills(self) -> RedundancyReport:
        """Scan all ACTIVE skills and return a RedundancyReport."""
        active = self.sm.list_by_status(SkillStatus.ACTIVE)
        report = RedundancyReport(active_skill_count=len(active))

        if len(active) < 2:
            return report

        # Pre-compute SimHash fingerprints (性能优化，保留)
        from slim_agent.slim_reducer.simhash import simhash
        fingerprints = {s.id: simhash(s.summary or "") for s in active}

        # Inject fingerprints into entries for registry signals
        for s in active:
            s._simhash_fp = fingerprints[s.id]

        # Pre-build BM25 index (借鉴 Qdrant embed 阶段)
        from slim_agent.slim_reducer.bm25 import BM25Index
        bm25_idx = BM25Index.from_skills(active)

        checked: set[tuple[int, int]] = set()
        suggestions: list[MergeSuggestion] = []
        candidate_pairs: list[tuple[Any, Any, list[dict]]] = []

        for i, skill in enumerate(active):
            for other in active[i + 1:]:
                pair = tuple(sorted([skill.id, other.id]))
                if pair in checked:
                    continue
                checked.add(pair)

                # 用 Registry 评估所有信号
                hits = self.registry.evaluate(skill, other)
                if not hits:
                    continue

                # BM25 信号（单独计算，不在 registry 中以避免 index 依赖）
                from slim_agent.slim_reducer.bm25 import bm25_signal
                bm25_score = bm25_signal(skill, other, index=bm25_idx)
                if bm25_score >= 0.15:
                    hits.append({
                        'name': 'bm25',
                        'score': round(bm25_score, 4),
                        'threshold': 0.15,
                        'weight': 1.5,  # BM25 权重略高（借鉴 Qdrant hybrid search）
                    })

                if not hits:
                    continue

                candidate_pairs.append((skill, other, hits))

        # RRF 融合（借鉴 Qdrant prefetch+rescore 两阶段）
        from slim_agent.slim_reducer.rrf import rrf_combine_pairs
        ranked = rrf_combine_pairs(candidate_pairs)

        for rrf_score, (skill, other), hits in ranked:
            # 渐进式分级
            severity = self._classify_severity(rrf_score)

            # 生成 reason
            signal_strs = [f"{h['name']}={h['score']:.2f}" for h in hits]
            shared_tags = sorted(set(skill.tags or []) & set(other.tags or []))

            suggestions.append(MergeSuggestion(
                skill_ids=[skill.id, other.id],
                skill_names=[skill.name, other.name],
                shared_tags=shared_tags,
                overlap_score=round(rrf_score, 3),
                reason=f"Overlap signals (RRF={rrf_score:.3f}): {', '.join(signal_strs)}. Shared tags: {len(shared_tags)}",
                severity=severity,
            ))

        report.suggestions = suggestions

        # 循环检测：如果连续产生相同建议
        if report.suggestions:
            fp = ",".join(sorted(str(s.skill_ids) for s in report.suggestions))
            nudge = self.loop_detector.check("scan", fp)
            if nudge.level != 'ok':
                report.nudge = nudge.message

        return report

    @staticmethod
    def _classify_severity(score: float) -> str:
        """渐进式分级"""
        if score >= 0.8:
            return 'critical'   # 几乎重复，强烈建议合并
        if score >= 0.5:
            return 'warning'    # 有明显重叠
        if score >= 0.3:
            return 'info'        # 轻微重叠
        return 'ok'
