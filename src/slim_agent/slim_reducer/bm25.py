"""BM25-style keyword matching signal for skill similarity.

借鉴: Qdrant lib/bm25/ TF/IDF 分离设计
来源: https://github.com/qdrant/qdrant
许可: Apache-2.0（仅借鉴设计思想，代码完全重写）

核心设计思想（来自 Qdrant）:
  - TF 权重在 embedding 阶段计算（文档索引时）
  - IDF 在查询阶段动态注入（查询时用 collection 级统计）
  - Token ID 用 murmur3 hash 保证一致性

slim-agent 实现:
  - 无需 murmur3（技能数量小，直接用 word）
  - TF/IDF 分离思想保留
  - IDF 用简化版: log(N/df + 1)
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from slim_agent.skill_manager.models import SkillEntry

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


@dataclass
class BM25Index:
    """轻量 BM25 倒排索引，用于 skill summary 的关键词匹配。

    TF/IDF 分离设计（借鉴 Qdrant）:
      - build() 时计算 TF 权重 → 存入 token_weights
      - query() 时注入 IDF 权重（基于全量 df 统计）
    """

    k1: float = 1.2      # TF 饱和参数
    b: float = 0.75       # 文档长度归一化
    avg_doc_len: float = 0.0
    total_docs: int = 0
    df: Counter = field(default_factory=Counter)  # term → 文档频率
    # skill_id → { term → tf_weight }
    token_weights: dict[int, dict[str, float]] = field(default_factory=dict)
    doc_lens: dict[int, int] = field(default_factory=dict)

    @classmethod
    def from_skills(cls, skills: list, k1: float = 1.2, b: float = 0.75) -> BM25Index:
        """从 skill 列表构建 BM25 索引（Qdrant 的 embed 阶段）"""
        idx = cls(k1=k1, b=b)
        idx.total_docs = len(skills)

        if idx.total_docs == 0:
            return idx

        # 计算 TF 权重（Qdrant embed_document 逻辑）
        for skill in skills:
            tokens = _TOKEN_RE.findall((skill.summary or "").lower())
            tf = Counter(tokens)
            doc_len = len(tokens)
            idx.doc_lens[skill.id] = doc_len

            weights: dict[str, float] = {}
            for term, n in tf.items():
                idx.df[term] += 1
                # BM25 TF 权重公式（Qdrant 公式）
                weights[term] = n * (k1 + 1) / (k1 * (1 - b + b * doc_len / 256) + n)
            idx.token_weights[skill.id] = weights

        # 平均文档长度
        idx.avg_doc_len = sum(idx.doc_lens.values()) / max(idx.total_docs, 1)

        return idx

    def score_pair(self, id_a: int, id_b: int) -> float:
        """计算两个 skill 之间的 BM25 相似度（Qdrant query 逻辑）。

        对 skill_a 的每个 term，注入 IDF 后查询 skill_b 的 tf 权重，累加。
        """
        if self.total_docs < 2:
            return 0.0

        tokens_a = self.token_weights.get(id_a, {})
        tokens_b = self.token_weights.get(id_b, {})
        if not tokens_a or not tokens_b:
            return 0.0

        # 注入 IDF 权重（Qdrant fancy_idf 逻辑，简化版）
        idf_cache: dict[str, float] = {}
        total_score = 0.0

        for term, tf_weight in tokens_a.items():
            if term not in idf_cache:
                df_i = self.df.get(term, 0)
                # Wikipedia-style BM25 IDF（Qdrant fancy_idf 变体，简化）
                idf_cache[term] = math.log((self.total_docs - df_i + 0.5) / (df_i + 0.5) + 1)

            idf = idf_cache[term]
            tf_b = tokens_b.get(term, 0.0)
            total_score += idf * tf_b

        # 归一化：除以 query term 数量，得到 0~1 范围
        n_terms = len(tokens_a)
        if n_terms == 0:
            return 0.0

        raw = total_score / n_terms

        # 用 Sigmoid 压缩到 [0, 1]
        return 1.0 / (1.0 + math.exp(-raw + 2))


def bm25_signal(a, b, index: BM25Index | None = None) -> float:
    """BM25 keyword similarity signal handler (for SignalRegistry).

    如果没有预建索引，会退化为 word Jaccard。
    """
    if index is None:
        # 无索引时退化为 word overlap ratio
        wa = set(_TOKEN_RE.findall((a.summary or "").lower()))
        wb = set(_TOKEN_RE.findall((b.summary or "").lower()))
        if not wa and not wb:
            return 0.0
        return len(wa & wb) / len(wa | wb) if (wa | wb) else 0.0

    return index.score_pair(a.id, b.id)
