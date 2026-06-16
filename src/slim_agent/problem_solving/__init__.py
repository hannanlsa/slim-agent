"""problem_solving — Q4 问题驱动学习协调器

4 步流程：记录问题 → 根源追踪（WebSearch 验证）→ 学习验证 → 沉淀
沉淀层：基于 versioned_reflection (Q3) 基础设施

公开 API:
- learn_problem / learn_manual / learn_from_error / record_evolution
- list_learnings / get_learning / rollback_learning / diff_learning / search_learnings
- SOURCE_AGENT / SOURCE_ERROR / SOURCE_MANUAL / SOURCE_EVOLUTION 常量
"""
from __future__ import annotations

# Re-export from core
from slim_agent.problem_solving.core import (
    # 触发源常量
    SOURCE_AGENT,
    SOURCE_ERROR,
    SOURCE_MANUAL,
    SOURCE_EVOLUTION,
    # 学习入口
    learn_problem,
    learn_manual,
    learn_from_error,
    record_evolution,
    # 查询 API
    list_learnings,
    get_learning,
    rollback_learning,
    diff_learning,
    search_learnings,
)

__all__ = [
    "SOURCE_AGENT",
    "SOURCE_ERROR",
    "SOURCE_MANUAL",
    "SOURCE_EVOLUTION",
    "learn_problem",
    "learn_manual",
    "learn_from_error",
    "record_evolution",
    "list_learnings",
    "get_learning",
    "rollback_learning",
    "diff_learning",
    "search_learnings",
]
