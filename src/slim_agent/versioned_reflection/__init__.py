"""versioned_reflection — Q3 增量 diff 版本管理经验沉淀

基于 Git 增量 diff 思想，将 reflection_pool 升级为：
- 每次 update 生成 unified diff patch 存入 <slug>.history/
- rollback 通过 patch -R (或纯 Python 重建) 回到指定版本
- 版本号永远递增（避免 patch 链冲突）
- _rebuild_index 兜底：JSON 索引损坏时从 reflections/ 目录扫描重建

公开 API:
- ReflectionEntry dataclass
- create_entry / update_entry / get_entry / list_entries / search_entries
- rollback / diff_entry / history
- bump_trigger
- POOL_DIR / INDEX_PATH 常量
- init_pool()
"""
from __future__ import annotations

import os
import sys

# Re-export all public API from core.py
from slim_agent.versioned_reflection.core import (
    # Constants
    POOL_DIR,
    INDEX_PATH,
    # Data class
    ReflectionEntry,
    # Core API
    init_pool,
    create_entry,
    update_entry,
    get_entry,
    list_entries,
    search_entries,
    rollback,
    diff_entry,
    history,
    bump_trigger,
    # Internal helpers (公开供 CLI / 调试使用)
    _entry_path,
    _history_dir,
    _history_patches,
    _read_index,
    _rebuild_index,
    _write_index,
    _parse_frontmatter,
    _render_markdown,
    _generate_patch,
    _apply_patches_to_empty,
    _apply_patch_pure,
    _parse_hunks,
    _slugify,
    _ensure_dirs,
    _fmt,
    _parse_tags,
)

__all__ = [
    "POOL_DIR",
    "INDEX_PATH",
    "ReflectionEntry",
    "init_pool",
    "create_entry",
    "update_entry",
    "get_entry",
    "list_entries",
    "search_entries",
    "rollback",
    "diff_entry",
    "history",
    "bump_trigger",
]
