#!/usr/bin/env python3
"""
retrieval_reflex.py — P1.1 模拟人脑提升: Retrieval Reflex

核心功能：
1. extract_entities(text) — 从文本中自动提取 salient entity (正则提取)
2. reflex_search(entities, store) — 对每个 entity 调用 memory_search
3. inject_context(hits) — 将搜索结果组装为 context 注入块

设计借鉴：GBrain 的 Retrieval Reflex（自动检测 salient entity + 注入 context）
实现方式：正则提取实体名 → 调用 PointerStore.search_by_keyword → 结果注入

ponytail: L3 regex-ok | 已知限制：正则无法提取隐含实体（如"那个项目"） | 升级：加 NLP NER
"""
from __future__ import annotations

import re
from typing import Any, Optional

from slim_agent.pointer_memory.store import PointerStore


# ─── 实体提取正则 ──────────────────────────────────────────────────────────────

# CamelCase (2+ 大写字母交替): OpenHuman, SlimReducer, SimHash
_CAMEL_CASE = re.compile(r'[A-Z][a-z]+[A-Z][A-Za-z]+')

# hyphen/underscore compound (2+ segments): slim-agent, BM25_algorithm
_HYPHEN_US = re.compile(r'[A-Za-z]+[-_][A-Za-z]+[-_A-Za-z]*')

# quoted proper nouns: "GBrain", "Karpathy"
_QUOTED_NAME = re.compile(r'"([A-Za-z][A-Za-z0-9 ]+)"')

# CJK entity (2+ chars): 模拟人脑, 问题驱动
_CJK_ENTITY = re.compile(r'[\u4e00-\u9fff]{2,6}')

# Known project/person patterns (common open-source names)
_KNOWN_NAMES = re.compile(
    r'(?i)\b(openhuman|superpowers|ars|ponytail|gbrain|horizon|'
    r'agentmemory|hermes|karpathy|mattpocock|ecc|openclaw|qclaw|'
    r'slim-agent|slimreducer|simhash|bm25|rrf|fts5|sqlite|click)\b'
)


def extract_entities(text: str) -> list[str]:
    """
    从文本中提取 salient entity names.

    Returns a deduplicated list of entity strings found in the text.
    Uses multiple regex patterns to catch:
    - CamelCase compound names (OpenHuman, SimHash)
    - hyphen/underscore compounds (slim-agent, BM25_algorithm)
    - Quoted proper nouns ("GBrain")
    - CJK compound terms (模拟人脑, 问题驱动)
    - Known project/person names (OpenHuman, GBrain, etc.)

    ponytail: L3 regex-ok | 已知限制：正则无法提取隐含实体 | 升级：加 NLP NER
    """
    entities: list[str] = []

    # CamelCase
    for m in _CAMEL_CASE.finditer(text):
        entities.append(m.group())

    # hyphen/underscore compounds
    for m in _HYPHEN_US.finditer(text):
        entities.append(m.group())

    # quoted proper nouns
    for m in _QUOTED_NAME.finditer(text):
        entities.append(m.group(1))

    # CJK entities
    for m in _CJK_ENTITY.finditer(text):
        entities.append(m.group())

    # known names
    for m in _KNOWN_NAMES.finditer(text):
        entities.append(m.group())

    # Deduplicate (preserve order)
    seen = set()
    result = []
    for e in entities:
        normalized = e.lower().replace('-', '_').replace(' ', '_')
        if normalized not in seen:
            seen.add(normalized)
            result.append(e)

    return result


def reflex_search(
    entities: list[str],
    store: Optional[PointerStore] = None,
    db_path: str = "slim_agent.db",
) -> list[dict[str, Any]]:
    """
    For each entity, search PointerStore and collect hits.

    Args:
        entities: list of entity strings from extract_entities()
        store: existing PointerStore (if None, creates one from db_path)
        db_path: fallback DB path if store is None

    Returns:
        list of {entity, pointer_id, summary, primary_url, tags} dicts
    """
    if store is None:
        store = PointerStore(db_path)

    hits: list[dict[str, Any]] = []
    for entity in entities:
        results = store.search_by_keyword(entity)
        for r in results:
            hits.append({
                "entity": entity,
                "pointer_id": r.id,
                "summary": r.summary,
                "primary_url": r.primary_url,
                "tags": r.tags,
            })

    if store is None:
        # We created it, close it
        pass  # PointerStore auto-closes is optional

    return hits


def inject_context(
    hits: list[dict[str, Any]],
    max_items: int = 5,
) -> str:
    """
    Assemble search hits into a context injection block.

    Returns a formatted string suitable for injecting into an agent's
    system prompt or conversation context.

    Args:
        hits: list of {entity, pointer_id, summary, primary_url, tags} dicts
        max_items: maximum number of items to include (token budget control)

    Returns:
        formatted context block string
    """
    if not hits:
        return ""

    # Deduplicate by pointer_id (keep first occurrence)
    seen_ids = set()
    unique_hits = []
    for h in hits:
        if h["pointer_id"] not in seen_ids:
            seen_ids.add(h["pointer_id"])
            unique_hits.append(h)

    # Limit to max_items (token budget)
    items = unique_hits[:max_items]

    lines = ["[Retrieval Reflex — auto-injected context]", ""]
    for h in items:
        tags_str = ", ".join(h["tags"]) if h["tags"] else ""
        lines.append(f"• {h['entity']} → {h['summary'][:60]}")
        lines.append(f"  URL: {h['primary_url']}")
        if tags_str:
            lines.append(f"  Tags: {tags_str}")
    lines.append("")
    lines.append(f"(auto-injected {len(items)} of {len(unique_hits)} hits)")

    return "\n".join(lines)


# ─── self-test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Test entity extraction
    text = "OpenHuman uses SimHash for CJK text. slim-agent follows GBrain patterns."
    entities = extract_entities(text)
    print(f"Entities: {entities}")

    # Expected: some subset of [OpenHuman, SimHash, slim-agent, CJK, GBrain]
    assert len(entities) > 0, "should extract at least some entities"

    # Test known-name extraction
    text2 = "GBrain has Retrieval Reflex and Dream Cycle features"
    entities2 = extract_entities(text2)
    print(f"Entities2: {entities2}")
    assert "GBrain" in entities2, "should extract GBrain from known names"

    # Test CJK extraction
    text3 = "模拟人脑是P1方向，问题驱动学习是P5"
    entities3 = extract_entities(text3)
    print(f"Entities3: {entities3}")
    assert any("模拟人脑" in e or "问题驱动" in e for e in entities3), "should extract CJK entities"

    # Test inject_context formatting
    mock_hits = [
        {"entity": "SimHash", "pointer_id": 1, "summary": "BLAKE2b 64-bit fingerprint", "primary_url": "https://example.com", "tags": ["simhash", "fingerprint"]},
        {"entity": "GBrain", "pointer_id": 2, "summary": "AI memory system by Garry Tan", "primary_url": "https://github.com/garrytan/gbrain", "tags": ["gbrain", "memory"]},
    ]
    context = inject_context(mock_hits)
    print(f"Context:\n{context}")
    assert "[Retrieval Reflex" in context, "should have header"
    assert "SimHash" in context, "should mention entity"

    print("\n✅ All self-tests passed")
