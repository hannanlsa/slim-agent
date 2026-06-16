"""RRF (Reciprocal Rank Fusion) score combiner.

借鉴: Qdrant lib/collection/ RRF 实现
来源: https://github.com/qdrant/qdrant
许可: Apache-2.0（仅借鉴公式，代码完全重写）

核心设计思想（来自 Qdrant）:
  - RRF 只看排名不看分数，天然对分数尺度鲁棒
  - 公式: score = 1 / ((rank + offset) / weight + k)
  - prefetch + rescore 两阶段：各信号独立搜索 → RRF 融合

slim-agent 实现:
  - 每个 SignalRegistry 信号独立产出排名
  - RRF 融合多信号排名为最终分数
  - 替代原来的 "max(all scores)" 策略
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Qdrant 默认 k=60，slim-agent 技能数量少，用 k=5
_DEFAULT_K = 5
_DEFAULT_OFFSET = 1


@dataclass
class _RankedItem:
    skill_id: int
    rank: int
    weight: float = 1.0
    signal_name: str = ""


def rrf_combine(
    signals_by_pair: dict[tuple[int, int], list[dict]],
    k: float = _DEFAULT_K,
    offset: float = _DEFAULT_OFFSET,
) -> dict[tuple[int, int], float]:
    """RRF 融合多信号排名。

    Args:
        signals_by_pair: {(id_a, id_b): [{'name': ..., 'score': ..., 'weight': ...}, ...]}
            每个 pair 的所有已触发信号（已有 score >= threshold）
        k: RRF 常数（Qdrant 用 60，slim-agent 用 5）
        offset: 排名偏移（Qdrant 用 1）

    Returns:
        {(id_a, id_b): rrf_score}  — 融合后的分数

    Qdrant RRF 公式（借鉴）:
        score = Σ_i  1 / ((rank_i + offset) / weight_i + k)

    简化: 单 pair 内每个信号视为第 1 名（因为只有 2 个 skill 在比较），
    但保留 weight 支持。实际效果是加权信号数量的倒数和。
    """
    result: dict[tuple[int, int], float] = {}

    for pair, hits in signals_by_pair.items():
        if not hits:
            continue

        # Qdrant 的 RRF：每个信号独立排名后融合
        # slim-agent 每个 pair 只有 A vs B，排名恒为 1
        # 所以简化为: rrf = Σ weight_i / (offset + k) = n_signals * weight / (offset + k)
        # 但保留可扩展性：如果未来引入 N-ary 比较，排名才有意义
        rrf_sum = 0.0
        for h in hits:
            rank = 1  # 二元比较恒为 1
            w = h.get('weight', 1.0)
            rrf_sum += 1.0 / ((rank + offset) / w + k)

        # 归一化到 [0, 1]: 用 Sigmoid 压缩
        import math
        result[pair] = 1.0 / (1.0 + math.exp(-rrf_sum + 1))

    return result


def rrf_combine_pairs(
    candidate_pairs: list[tuple[Any, Any, list[dict]]],
    k: float = _DEFAULT_K,
    offset: float = _DEFAULT_OFFSET,
) -> list[tuple[float, tuple[Any, Any], list[dict]]]:
    """对多对 skill-信号 做 Rankings-based RRF 融合。

    Args:
        candidate_pairs: [(skill_a, skill_b, [signal_hits]), ...]
        k: RRF 常数
        offset: 排名偏移

    Returns:
        [(rrf_score, (skill_a, skill_b), signal_hits), ...]  — 按 score 降序
    """
    scored = []
    for a, b, hits in candidate_pairs:
        if not hits:
            continue

        rrf_sum = 0.0
        for h in hits:
            rank = 1
            w = h.get('weight', 1.0)
            rrf_sum += 1.0 / ((rank + offset) / w + k)

        import math
        score = 1.0 / (1.0 + math.exp(-rrf_sum + 1))
        scored.append((score, (a, b), hits))

    scored.sort(key=lambda x: x[0], reverse=True)
    return scored
