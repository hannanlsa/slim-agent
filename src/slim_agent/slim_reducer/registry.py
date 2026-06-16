"""
Signal Registry — 动态信号注册系统 for SlimReducer.

借鉴: browser-use controller/ Registry + Decorator 模式
来源: ~/.qclaw/skills/action-registry/SKILL.md

将 SlimReducer 的硬编码三信号（tag Jaccard / word Jaccard / SimHash）
改为可动态注册/禁用/配置的 Registry。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class SignalEntry:
    """一个去重信号的定义"""

    name: str
    handler: Callable  # (a: SkillEntry, b: SkillEntry) -> float  返回 0.0-1.0
    threshold: float = 0.3
    weight: float = 1.0
    enabled: bool = True
    description: str = ""


class SignalRegistry:
    """动态信号注册中心 — SlimReducer 用它替代硬编码信号"""

    def __init__(self) -> None:
        self._signals: dict[str, SignalEntry] = {}

    def register(self, name: str, threshold: float = 0.3,
                 weight: float = 1.0, description: str = ""):
        """装饰器：注册一个信号"""
        def decorator(fn: Callable) -> Callable:
            self._signals[name] = SignalEntry(
                name=name,
                handler=fn,
                threshold=threshold,
                weight=weight,
                description=description or fn.__doc__ or '',
            )
            return fn
        return decorator

    def add(self, entry: SignalEntry) -> None:
        """直接添加一个信号"""
        self._signals[entry.name] = entry

    def disable(self, name: str) -> None:
        if name in self._signals:
            self._signals[name].enabled = False

    def enable(self, name: str) -> None:
        if name in self._signals:
            self._signals[name].enabled = True

    def list_enabled(self) -> list[SignalEntry]:
        return [s for s in self._signals.values() if s.enabled]

    def get(self, name: str) -> SignalEntry | None:
        return self._signals.get(name)

    def evaluate(self, a: Any, b: Any) -> list[dict]:
        """对所有已启用信号求值，返回触发列表"""
        hits = []
        for signal in self.list_enabled():
            score = signal.handler(a, b)
            if score >= signal.threshold:
                hits.append({
                    'name': signal.name,
                    'score': round(score, 4),
                    'threshold': signal.threshold,
                    'weight': signal.weight,
                })
        return hits


# ── 默认三信号（向后兼容） ──────────────────────────────────

def _tag_jaccard(a, b) -> float:
    """Tag 集合 Jaccard 相似度"""
    sa, sb = set(a.tags or []), set(b.tags or [])
    if not sa and not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _word_jaccard(a, b) -> float:
    """摘要 word-level Jaccard"""
    wa = set((a.summary or "").lower().split())
    wb = set((b.summary or "").lower().split())
    if not wa and not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def _simhash_score(a, b) -> float:
    """摘要 SimHash 相似度"""
    from slim_agent.slim_reducer.simhash import simhash, simhash_similarity
    fp_a = simhash(a.summary or "")
    fp_b = simhash(b.summary or "")
    return simhash_similarity(fp_a, fp_b)


def create_default_registry() -> SignalRegistry:
    """创建带三个默认信号的 Registry"""
    reg = SignalRegistry()
    reg.add(SignalEntry(
        name='tag_jaccard',
        handler=_tag_jaccard,
        threshold=0.3,
        weight=1.0,
        description='Tag 集合 Jaccard 相似度',
    ))
    reg.add(SignalEntry(
        name='word_jaccard',
        handler=_word_jaccard,
        threshold=0.5,  # 比 tag 更严格
        weight=1.0,
        description='摘要 word-level Jaccard',
    ))
    reg.add(SignalEntry(
        name='simhash',
        handler=_simhash_score,
        threshold=0.65,
        weight=1.0,
        description='摘要 SimHash 相似度（CJK + paraphrase robust）',
    ))
    return reg
