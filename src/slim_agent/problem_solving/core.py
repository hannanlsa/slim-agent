#!/usr/bin/env python3
"""
problem_solving.py — 问题驱动学习 (Problem-Driven Learning) 协调器

设计哲学：
- 不是 cron 定时同步，是遇到真实问题才触发
- 流程：记录问题 → 根源追踪（强制 WebSearch 验证） → 学习验证 → 沉淀
- 沉淀层：基于 reflection_pool (Q3 基础设施)，使用 source=problem_learning 标签
- 三类触发源：
  1. 任务中遇到未知 (slim-agent runtime exception)
  2. 错误反思 (reflection_pool 自然触发)
  3. 主人显式指令 ("学习 X")

与现有机制关系：
- skill-auto-trigger: 被动调用（用户给任务时自动加载）
- self-improvement: 定时回顾（self_reflection.py）
- problem-solving: 按需主动学习（这次 Q4）

公开 API：
- learn_problem(problem, *, source='agent', tags=None, reason='', websearch_fn=None)
- learn_manual(topic, *, reason='', tags=None)
- learn_from_error(error_type, error_message, *, context='', lesson='', related_skill=None)
- list_learnings(source=None, tag=None) -> list[dict]
- get_learning(slug) -> dict
- rollback_learning(slug, to_version) -> dict
- diff_learning(slug, against_version=1) -> str
"""
from __future__ import annotations

import os
import re
import json
import time
import datetime as dt
from typing import Optional, Callable

from slim_agent.versioned_reflection import core as rp


# ─── 触发源常量 ────────────────────────────────────────────────────────────────

SOURCE_AGENT = "agent"               # slim-agent 运行时遇到未知
SOURCE_ERROR = "error"               # 错误反思
SOURCE_MANUAL = "manual"             # 主人显式指令
SOURCE_EVOLUTION = "evolution"       # 进化追踪（slim-agent 自我迭代）


# ─── 核心 API ──────────────────────────────────────────────────────────────────

def learn_problem(
    problem: str,
    *,
    source: str = SOURCE_AGENT,
    tags: Optional[list[str]] = None,
    reason: str = "",
    websearch_fn: Optional[Callable[[str], list[dict]]] = None,
) -> dict:
    """
    问题驱动学习主入口

    Args:
        problem: 问题描述（"为什么 slim-agent 的 reflection_pool rollback 后 update 产生重复版本号"）
        source: 触发源 (agent / error / manual / evolution)
        tags: 标签（默认自动生成）
        reason: 学习原因
        websearch_fn: 外部注入的 WebSearch 函数（避免硬依赖），返回 [{title, url, snippet}, ...]

    Returns:
        dict: {slug, version, status, references, lesson}
    """
    # 1. 规范化标题
    title = problem.strip().split('\n')[0][:120]  # 取首行，截断
    if not title:
        raise ValueError("problem 不能为空")

    # 2. 根源追踪 (WebSearch 验证)
    references = []
    if websearch_fn:
        try:
            references = websearch_fn(problem)[:5]  # 最多 5 条
        except Exception as e:
            references = [{"error": f"websearch failed: {e}"}]

    # 3. 构建内容（含 references 块）
    content_parts = [
        "## Problem",
        "",
        problem,
        "",
        "## Root Cause Analysis",
        "",
    ]
    if references:
        content_parts.append("WebSearch 验证：")
        content_parts.append("")
        for i, ref in enumerate(references, 1):
            if "error" in ref:
                content_parts.append(f"- ⚠ {ref['error']}")
            else:
                content_parts.append(f"- [{ref.get('title', 'untitled')}]({ref.get('url', '#')})")
                if ref.get('snippet'):
                    content_parts.append(f"  > {ref['snippet'][:200]}")
        content_parts.append("")
    else:
        content_parts.append("（无外部验证，由主人或 agent 自行确认）")
        content_parts.append("")

    content_parts.extend([
        "## Lesson Learned",
        "",
        "(待总结：完成学习后由 agent 或主人填写)",
        "",
        "## References",
        "",
    ])
    for i, ref in enumerate(references, 1):
        if "error" not in ref:
            content_parts.append(f"{i}. {ref.get('url', 'N/A')}")

    content = "\n".join(content_parts)

    # 4. 自动生成 tags
    if tags is None:
        tags = _extract_tags_from_problem(problem)
        if source and source not in tags:
            tags.append(source)

    # 5. 写入 reflection_pool
    entry = rp.create_entry(
        title=title,
        content=content,
        source=source,  # type: ignore[arg-type]
        tags=tags,
        reason=reason or f"problem-driven learning: {source}",
        summary=problem[:80].strip(),
    )

    return {
        "slug": entry.slug,
        "version": entry.version,
        "status": "recorded",
        "references": references,
        "lesson": "(待填写)",
    }


def learn_manual(
    topic: str,
    *,
    reason: str = "",
    tags: Optional[list[str]] = None,
) -> dict:
    """
    主人显式指令触发的学习

    与 learn_problem 的区别：
    - source=manual
    - 不强制 WebSearch（主人已经给过上下文）
    - title 用 topic 而不是 problem
    """
    return learn_problem(
        problem=topic,
        source=SOURCE_MANUAL,
        tags=tags or ["manual", "主人指令"],
        reason=reason or "主人显式指令触发",
        websearch_fn=None,
    )


def learn_from_error(
    error_type: str,
    error_message: str,
    *,
    context: str = "",
    lesson: str = "",
    related_skill: Optional[str] = None,
    tags: Optional[list[str]] = None,
) -> dict:
    """
    错误反思触发的学习

    与 learn_problem 的区别：
    - source=error
    - 内容结构化（problem / context / lesson）
    - 可关联 skill
    - 必须包含 context 和 lesson（One-Check Rule：无教训不算学习）
    """
    # ponytail: One-Check Rule — learn_from_error 必须有 context + lesson
    assert context, f"learn_from_error requires context (got empty). error_type={error_type}"
    assert lesson, f"learn_from_error requires lesson (got empty). error_type={error_type}"

    problem = f"{error_type}: {error_message}"
    content_parts = [
        "## Error",
        "",
        f"**Type**: `{error_type}`",
        f"**Message**: {error_message}",
        "",
    ]
    if context:
        content_parts.extend([
            "## Context",
            "",
            context,
            "",
        ])
    content_parts.extend([
        "## Lesson Learned",
        "",
        lesson or "(待总结)",
        "",
    ])
    if related_skill:
        content_parts.extend([
            "## Related Skill",
            "",
            f"`{related_skill}`",
            "",
        ])

    content = "\n".join(content_parts)

    auto_tags = tags or ["error", error_type.lower().replace("error", "").replace("exception", "")]
    if related_skill and related_skill not in auto_tags:
        auto_tags.append(related_skill)

    entry = rp.create_entry(
        title=problem,
        content=content,
        source=SOURCE_ERROR,
        tags=auto_tags,
        reason=f"error reflection: {error_type}",
        summary=error_message[:80].strip(),
    )

    return {
        "slug": entry.slug,
        "version": entry.version,
        "status": "recorded",
        "related_skill": related_skill,
    }


# ─── 查询 API ─────────────────────────────────────────────────────────────────

def list_learnings(
    source: Optional[str] = None,
    tag: Optional[str] = None,
) -> list[dict]:
    """列出所有问题驱动学习条目（可按 source / tag 过滤）"""
    return rp.list_entries(source=source, tag=tag)


def get_learning(slug: str) -> Optional[dict]:
    """获取指定 slug 的学习条目（含完整内容）"""
    entry = rp.get_entry(slug)
    if not entry:
        return None
    return {
        "slug": entry.slug,
        "title": entry.title,
        "content": entry.content,
        "version": entry.version,
        "source": entry.source,
        "tags": entry.tags,
        "reason": entry.reason,
        "summary": entry.summary,
        "created": entry.created,
        "modified": entry.modified,
        "patch_count": entry.patch_count,
        "trigger_count": entry.trigger_count,
    }


def rollback_learning(slug: str, to_version: int) -> Optional[dict]:
    """回滚学习条目到指定版本（基于 reflection_pool 的 rollback）"""
    entry = rp.rollback(slug, to_version=to_version)
    if not entry:
        return None
    return {
        "slug": entry.slug,
        "version": entry.version,
        "content": entry.content,
    }


def diff_learning(slug: str, against_version: int = 1) -> str:
    """对比当前学习条目与指定版本"""
    return rp.diff_entry(slug, against_version=against_version)


def search_learnings(query: str, source: Optional[str] = None) -> list[dict]:
    """搜索学习条目"""
    return rp.search_entries(query, source=source)


# ─── 进化追踪（与 evolution-tracker.jsonl 集成）────────────────────────────────

def record_evolution(
    capability: str,
    *,
    before: str = "",
    after: str = "",
    evidence: str = "",
    tags: Optional[list[str]] = None,
) -> dict:
    """
    记录一次能力进化（Q4 沉淀到 evolution-tracker.jsonl 的一部分）

    关键区别于 learn_problem：
    - learn_problem 是"遇到问题→解决"
    - record_evolution 是"能力提升→归档"
    """
    title = f"[Evolution] {capability}"
    content_parts = [
        "## Capability",
        "",
        capability,
        "",
    ]
    if before:
        content_parts.extend(["## Before", "", before, ""])
    if after:
        content_parts.extend(["## After", "", after, ""])
    if evidence:
        content_parts.extend([
            "## Evidence",
            "",
            evidence,
            "",
        ])
    content_parts.extend([
        "## Triggered By",
        "",
        "(problem-driven learning / manual upgrade / 仓库学习借鉴)",
    ])
    content = "\n".join(content_parts)

    auto_tags = tags or ["evolution", "能力提升"]
    if capability and capability not in auto_tags:
        auto_tags.append(capability)

    entry = rp.create_entry(
        title=title,
        content=content,
        source=SOURCE_EVOLUTION,
        tags=auto_tags,
        reason=f"evolution: {capability}",
        summary=capability[:80].strip(),
    )

    # 同步到 evolution-tracker.jsonl
    _append_evolution_tracker({
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "capability": capability,
        "before": before,
        "after": after,
        "evidence": evidence,
        "slug": entry.slug,
    })

    return {
        "slug": entry.slug,
        "version": entry.version,
        "status": "recorded",
    }


# ─── 内部辅助 ─────────────────────────────────────────────────────────────────

def _extract_tags_from_problem(problem: str) -> list[str]:
    """从问题描述中自动提取标签"""
    # 简单关键词匹配
    keywords = {
        "click": "click", "sqlite": "sqlite", "python": "python",
        "reflection": "reflection", "rollback": "rollback",
        "version": "version", "patch": "patch", "diff": "diff",
        "fatal": "critical", "error": "error", "bug": "bug",
        "skill": "skill", "slim": "slim-agent",
    }
    tags = []
    problem_lower = problem.lower()
    for kw, tag in keywords.items():
        if kw in problem_lower and tag not in tags:
            tags.append(tag)
    return tags or ["uncategorized"]


def _append_evolution_tracker(record: dict) -> None:
    """追加到 evolution-tracker.jsonl"""
    tracker_path = os.path.expanduser("~/.qclaw/workspace/evolution-tracker.jsonl")
    os.makedirs(os.path.dirname(tracker_path), exist_ok=True)
    with open(tracker_path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ─── CLI 入口 ─────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="problem_solving — 问题驱动学习")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # learn subcommand
    p_learn = sub.add_parser("learn", help="记录一个问题（自动 websearch 验证）")
    p_learn.add_argument("problem", help="问题描述")
    p_learn.add_argument("--source", default=SOURCE_AGENT, choices=[SOURCE_AGENT, SOURCE_ERROR, SOURCE_MANUAL, SOURCE_EVOLUTION])
    p_learn.add_argument("--reason", default="")
    p_learn.add_argument("--tag", action="append", help="可重复加多个 tag")

    # manual subcommand
    p_manual = sub.add_parser("manual", help="主人显式指令触发")
    p_manual.add_argument("topic", help="学习主题")
    p_manual.add_argument("--reason", default="")

    # error subcommand
    p_error = sub.add_parser("error", help="错误反思触发")
    p_error.add_argument("error_type", help="错误类型")
    p_error.add_argument("error_message", help="错误信息")
    p_error.add_argument("--context", default="")
    p_error.add_argument("--lesson", default="")
    p_error.add_argument("--related-skill", default=None)

    # evolution subcommand
    p_evo = sub.add_parser("evolution", help="记录能力进化")
    p_evo.add_argument("capability", help="能力名称")
    p_evo.add_argument("--before", default="")
    p_evo.add_argument("--after", default="")
    p_evo.add_argument("--evidence", default="")

    # list subcommand
    p_list = sub.add_parser("list", help="列出所有学习条目")
    p_list.add_argument("--source", default=None)
    p_list.add_argument("--tag", default=None)

    # get subcommand
    p_get = sub.add_parser("get", help="获取学习条目")
    p_get.add_argument("slug")

    # rollback subcommand
    p_rb = sub.add_parser("rollback", help="回滚到指定版本")
    p_rb.add_argument("slug")
    p_rb.add_argument("--to", type=int, required=True)

    # diff subcommand
    p_diff = sub.add_parser("diff", help="对比版本")
    p_diff.add_argument("slug")
    p_diff.add_argument("--against", type=int, default=1)

    args = parser.parse_args()

    if args.cmd == "learn":
        result = learn_problem(args.problem, source=args.source, reason=args.reason, tags=args.tag)
        print(f"✅ Recorded: {result['slug']} (v{result['version']})")
    elif args.cmd == "manual":
        result = learn_manual(args.topic, reason=args.reason)
        print(f"✅ Recorded: {result['slug']} (v{result['version']})")
    elif args.cmd == "error":
        result = learn_from_error(args.error_type, args.error_message, context=args.context, lesson=args.lesson, related_skill=args.related_skill)
        print(f"✅ Recorded: {result['slug']} (v{result['version']})")
    elif args.cmd == "evolution":
        result = record_evolution(args.capability, before=args.before, after=args.after, evidence=args.evidence)
        print(f"✅ Recorded: {result['slug']} (v{result['version']})")
    elif args.cmd == "list":
        entries = list_learnings(source=args.source, tag=args.tag)
        for e in entries:
            print(f"[{e.get('source','?'):8}] {e['slug']:50} v{e['version']} {e.get('title','')[:60]}")
    elif args.cmd == "get":
        e = get_learning(args.slug)
        if e:
            print(f"slug: {e['slug']}")
            print(f"title: {e['title']}")
            print(f"version: {e['version']}")
            print(f"source: {e['source']}")
            print(f"tags: {e['tags']}")
            print(f"---")
            print(e['content'])
        else:
            print(f"❌ Not found: {args.slug}")
    elif args.cmd == "rollback":
        result = rollback_learning(args.slug, args.to)
        if result:
            print(f"✅ Rollback: {result['slug']} → v{result['version']}")
        else:
            print(f"❌ Rollback failed")
    elif args.cmd == "diff":
        print(diff_learning(args.slug, args.against))


if __name__ == "__main__":
    main()
