"""
Loop Detector — 渐进式循环检测 for SlimReducer.

借鉴: browser-use agent/prompts.py ActionLoopDetector
来源: ~/.qclaw/skills/loop-detector/SKILL.md

用于检测 reducer 是否对同一组 skill 反复产生相同建议，
或用户反复忽略某些建议（操作循环）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class NudgeResult:
    """循环检测结果"""
    level: str  # 'ok' | 'gentle' | 'warning' | 'critical'
    message: str = ""
    repetition_count: int = 0
    stagnant_count: int = 0


@dataclass
class LoopDetector:
    """渐进式循环检测器"""

    recent_actions: list[str] = field(default_factory=list)
    recent_states: list[str] = field(default_factory=list)
    repetition_count: int = 0
    stagnant_count: int = 0
    max_history: int = 20

    def check(self, action: str, state_fingerprint: str = "") -> NudgeResult:
        """检查是否进入循环"""
        self.recent_actions.append(action)
        if state_fingerprint:
            self.recent_states.append(state_fingerprint)

        # 保持窗口大小
        while len(self.recent_actions) > self.max_history:
            self.recent_actions.pop(0)
        while len(self.recent_states) > self.max_history:
            self.recent_states.pop(0)

        # 检测重复动作（最近 3 次相同）
        if len(self.recent_actions) >= 3:
            if (self.recent_actions[-1] == self.recent_actions[-2]
                    == self.recent_actions[-3]):
                self.repetition_count += 1
            else:
                self.repetition_count = 0

        # 检测停滞
        if len(self.recent_states) >= 3:
            if (self.recent_states[-1] == self.recent_states[-2]
                    == self.recent_states[-3]):
                self.stagnant_count += 1
            else:
                self.stagnant_count = 0

        return self._compute_nudge()

    def _compute_nudge(self) -> NudgeResult:
        if self.repetition_count >= 12:
            return NudgeResult('critical', '⚠️ 强烈建议停止当前操作并换方法',
                               self.repetition_count, self.stagnant_count)
        if self.stagnant_count >= 8:
            return NudgeResult('critical', '⚠️ 状态长时间未变化，当前操作可能无效',
                               self.repetition_count, self.stagnant_count)
        if self.repetition_count >= 8:
            return NudgeResult('warning', '💡 可能进入了循环，考虑换一种方式',
                               self.repetition_count, self.stagnant_count)
        if self.stagnant_count >= 5:
            return NudgeResult('warning', '💡 状态未变化，操作可能没有效果',
                               self.repetition_count, self.stagnant_count)
        if self.repetition_count >= 5:
            return NudgeResult('gentle', 'ℹ️ 注意：连续执行了相同操作',
                               self.repetition_count, self.stagnant_count)
        if self.stagnant_count >= 3:
            return NudgeResult('gentle', 'ℹ️ 状态连续几步未变化',
                               self.repetition_count, self.stagnant_count)
        return NudgeResult('ok', '', self.repetition_count, self.stagnant_count)

    def reset(self) -> None:
        """切换任务时重置"""
        self.recent_actions.clear()
        self.recent_states.clear()
        self.repetition_count = 0
        self.stagnant_count = 0
