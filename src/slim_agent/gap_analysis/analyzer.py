#!/usr/bin/env python3
"""
analyzer.py — P1.2 模拟人脑提升: Gap Analysis

核心功能：
1. analyze_gaps(question, hits, threshold) — 检查检索结果是否覆盖问题关键词
2. mark_gap(topic, confidence) — 生成 [MEMORY GAP: topic] 标注
3. format_gap_report(gaps) — 格式化 gap 报告

设计借鉴：GBrain 的 Gap Analysis（明确告知"不知道什么"）
实现方式：关键词覆盖率计算 + 显式 [MEMORY GAP] 标注

ponytail: L2 stdlib-ok | 已知限制：关键词覆盖 ≠语义覆盖 | 升级：加 embedding similarity
"""
from __future__ import annotations

import re
import dataclasses
from typing import Any, Optional


@dataclasses.dataclass
class GapAnnotation:
    """一条 memory gap 标注"""
    topic: str                    # 缺失的知识主题
    confidence: float = 0.0      # 检索置信度 (0-1, 越低越确定是 gap)
    missing_keywords: list[str] = dataclasses.field(default_factory=list)
    suggestion: str = ""         # 建议的补救方式 (如 "websearch" / "ask user")

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "confidence": self.confidence,
            "missing_keywords": self.missing_keywords,
            "suggestion": self.suggestion,
        }


def _extract_question_keywords(question: str) -> list[str]:
    """
    从问题中提取关键词（简单分词 + 去停用词）

    ponytail: L2 stdlib-ok | 已知限制：不分词CJK | 升级：jieba
    """
    # Remove punctuation, split on whitespace
    words = re.sub(r'[^\w\s]', ' ', question).split()

    # Stop words (English + common CJK particles)
    stop_words = {
        'what', 'is', 'how', 'does', 'why', 'are', 'the', 'a', 'an',
        'can', 'do', 'will', 'should', 'where', 'when', 'who', 'which',
        '的', '了', '是', '在', '有', '和', '与', '对', '为',
    }

    keywords = [w.lower() for w in words if w.lower() not in stop_words and len(w) > 1]

    # Also extract CJK compounds (2-4 chars)
    cjk_matches = re.findall(r'[\u4e00-\u9fff]{2,4}', question)
    keywords.extend(cjk_matches)

    return keywords


def analyze_gaps(
    question: str,
    hits: list[dict[str, Any]],
    threshold: float = 0.3,
) -> list[GapAnnotation]:
    """
    Analyze whether search results sufficiently cover the question.

    Algorithm:
    1. Extract keywords from the question
    2. Check which keywords appear in the search result summaries/tags
    3. Uncovered keywords → GapAnnotation with low confidence
    4. If coverage < threshold, mark the entire topic as a gap

    Args:
        question: the question being answered
        hits: search results (list of dicts with 'summary', 'tags', etc.)
        threshold: minimum keyword coverage ratio (0-1)

    Returns:
        list of GapAnnotation objects for uncovered areas
    """
    keywords = _extract_question_keywords(question)
    if not keywords:
        # No meaningful keywords → can't assess coverage
        return [GapAnnotation(
            topic=question[:60],
            confidence=0.0,
            missing_keywords=["(unable to extract keywords)"],
            suggestion="ask user for clarification",
        )]

    # Build searchable text from all hits
    searchable = ""
    for h in hits:
        searchable += (h.get("summary", "") or "") + " "
        searchable += " ".join(h.get("tags", []) or []) + " "

    searchable_lower = searchable.lower()

    # Check keyword coverage
    covered = [kw for kw in keywords if kw.lower() in searchable_lower]
    uncovered = [kw for kw in keywords if kw.lower() not in searchable_lower]

    coverage_ratio = len(covered) / len(keywords) if keywords else 0.0

    gaps: list[GapAnnotation] = []

    # If overall coverage is below threshold, mark as gap
    if coverage_ratio < threshold:
        gaps.append(GapAnnotation(
            topic=question[:60],
            confidence=coverage_ratio,
            missing_keywords=uncovered,
            suggestion="websearch" if not hits else "expand search terms",
        ))

    # Each uncovered keyword → individual gap annotation
    for kw in uncovered:
        if coverage_ratio >= threshold:
            # Still mark individual keyword gaps even if overall coverage is ok
            gaps.append(GapAnnotation(
                topic=f"detail on '{kw}'",
                confidence=0.0,
                missing_keywords=[kw],
                suggestion="websearch specific term",
            ))

    return gaps


def mark_gap(topic: str, confidence: float = 0.0) -> str:
    """
    Generate a [MEMORY GAP] annotation string.

    This is the core output format that should be used in agent responses
    when knowledge is insufficient.

    Args:
        topic: what the agent doesn't know
        confidence: retrieval confidence (0-1)

    Returns:
        formatted [MEMORY GAP: topic] annotation
    """
    if confidence > 0:
        return f"[MEMORY GAP: {topic}] (confidence: {confidence:.1%})"
    else:
        return f"[MEMORY GAP: {topic}]"


def format_gap_report(gaps: list[GapAnnotation]) -> str:
    """
    Format a list of GapAnnotations into a structured report.

    Returns:
        Multi-line report string suitable for agent output
    """
    if not gaps:
        return "[No memory gaps detected — all keywords covered]"

    lines = ["[Memory Gap Report]", ""]
    for g in gaps:
        annotation = mark_gap(g.topic, g.confidence)
        lines.append(annotation)
        if g.missing_keywords:
            lines.append(f"  Missing: {', '.join(g.missing_keywords)}")
        if g.suggestion:
            lines.append(f"  Suggestion: {g.suggestion}")
        lines.append("")

    lines.append(f"Total gaps: {len(gaps)}")
    return "\n".join(lines)


# ─── self-test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Test keyword extraction
    kws = _extract_question_keywords("What is SimHash and how does it work for CJK text?")
    print(f"Keywords: {kws}")
    assert "simhash" in kws, "should extract 'simhash'"
    assert "cjk" in kws, "should extract 'cjk'"
    assert "what" not in kws, "should remove stop word"

    # Test gap analysis with no hits
    gaps = analyze_gaps("What is SimHash?", hits=[], threshold=0.3)
    print(f"Gaps (no hits): {gaps}")
    assert len(gaps) > 0, "should detect gap when no hits"
    assert gaps[0].confidence == 0.0, "confidence should be 0 with no hits"

    # Test gap analysis with sufficient hits
    hits = [
        {"summary": "SimHash BLAKE2b 64-bit fingerprint for CJK text", "tags": ["simhash", "fingerprint", "cjk"], "primary_url": "https://example.com"}
    ]
    gaps2 = analyze_gaps("What is SimHash?", hits=hits, threshold=0.3)
    print(f"Gaps (good hits): {gaps2}")
    # SimHash keyword is covered → fewer or no gaps
    # Note: "simhash" should be in the hit summary

    # Test mark_gap formatting
    annotation = mark_gap("SimHash implementation details", confidence=0.15)
    print(f"Annotation: {annotation}")
    assert "[MEMORY GAP:" in annotation, "should contain MEMORY GAP marker"

    # Test format_gap_report
    report = format_gap_report([GapAnnotation(
        topic="SimHash internals",
        confidence=0.1,
        missing_keywords=["internals", "implementation"],
        suggestion="websearch",
    )])
    print(f"Report:\n{report}")
    assert "Memory Gap Report" in report, "should have header"

    print("\n✅ All self-tests passed")
