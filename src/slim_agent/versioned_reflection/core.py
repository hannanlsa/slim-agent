#!/usr/bin/env python3
"""
reflection_pool.py — ReflectionPool 版本管理核心模块

目录结构:
    ~/.qclaw/workspace/reflection-pool/
        pool_index.json          # 全量索引（版本 + 触发计数 + 来源）
        reflections/
            <slug>.md            # 当前版本正文
            <slug>.history/     # 演变历史（增量 patches）
                v1.patch        # 首次创建 patch
                v2.patch        # 第 1 次修改
                v3.patch        # 第 2 次修改
                ...

Patch 格式: unified diff
    Filename: v{N}.{unix_ts}.patch
    Header metadata: 版本号 / 创建时间 / 修改原因 / 来源标签

来源标签（source）:
    reflection       - 自我反思
    problem_learning - 问题驱动学习
    manual           - 手动创建
    evolution        - 进化追踪
"""

from __future__ import annotations

import dataclasses
import difflib
import json
import os
import re
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ─── 路径常量 ────────────────────────────────────────────────────────────────

# 默认存放于 ~/.qclaw/workspace/reflection-pool（保持与 OpenClaw skill 行为一致）
# 可通过环境变量 SLIM_AGENT_POOL_DIR 覆盖
WORKSPACE = os.environ.get("SLIM_AGENT_POOL_DIR") or os.path.join(
    os.path.expanduser("~"), ".qclaw", "workspace", "reflection-pool"
)
POOL_DIR = WORKSPACE
INDEX_PATH = os.path.join(POOL_DIR, "pool_index.json")
POOL_REFLECTIONS = os.path.join(POOL_DIR, "reflections")

# ─── 数据模型 ────────────────────────────────────────────────────────────────

@dataclasses.dataclass
class ReflectionEntry:
    """单条 Reflection 条目"""
    slug: str                    # URL-safe unique id (如 "context-error-logging")
    title: str                  # 可读标题
    content: str                 # 正文（Markdown）
    version: int = 1             # 当前版本号
    created: str = ""            # ISO timestamp
    modified: str = ""            # ISO timestamp
    patch_count: int = 0         # 已积累的 patch 数量
    trigger_count: int = 0        # 被触发的次数
    tags: list[str] = dataclasses.field(default_factory=list)
    source: str = "reflection"    # 来源标签
    reason: str = ""              # 最后一次修改原因
    summary: str = ""             # 一句话摘要（用于索引/搜索）

    def to_index_record(self) -> dict:
        return {
            "slug": self.slug,
            "title": self.title,
            "version": self.version,
            "created": self.created,
            "modified": self.modified,
            "patch_count": self.patch_count,
            "trigger_count": self.trigger_count,
            "tags": self.tags,
            "source": self.source,
            "reason": self.reason,
            "summary": self.summary,
        }


# ─── 核心工具函数 ────────────────────────────────────────────────────────────

def _slugify(text: str) -> str:
    """将标题转为 URL-safe slug"""
    import urllib.parse
    # 取前 40 字符，替换空格和特殊字符
    slug = re.sub(r'[^\w\s-]', '', text.lower())
    slug = re.sub(r'[-\s]+', '-', slug).strip('-')
    # 避免太长
    if len(slug) > 40:
        slug = slug[:40]
    return slug or "untitled"


def _ensure_dirs():
    """确保目录结构存在"""
    os.makedirs(POOL_REFLECTIONS, exist_ok=True)


def _entry_path(slug: str) -> str:
    return os.path.join(POOL_REFLECTIONS, f"{slug}.md")


def _history_dir(slug: str) -> str:
    return os.path.join(POOL_REFLECTIONS, f"{slug}.history")


def _history_patches(slug: str) -> list[str]:
    """返回 patch 文件列表（按版本排序）"""
    hist_dir = _history_dir(slug)
    if not os.path.exists(hist_dir):
        return []
    patches = [f for f in os.listdir(hist_dir) if f.endswith('.patch')]
    patches.sort()
    return [os.path.join(hist_dir, p) for p in patches]


def _read_index() -> dict:
    """读取索引（容错：JSON 损坏时从 reflections/ 重建）"""
    _ensure_dirs()
    if not os.path.exists(INDEX_PATH):
        return _rebuild_index()
    try:
        with open(INDEX_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"[WARN] pool_index.json corrupted ({e}), rebuilding...")
        return _rebuild_index()


def _rebuild_index() -> dict:
    """从 reflections/ 目录重建索引"""
    refl_dir = os.path.join(POOL_DIR, 'reflections')
    idx = {}
    if not os.path.exists(refl_dir):
        return {}
    for fname in os.listdir(refl_dir):
        if not fname.endswith('.md'):
            continue
        slug = fname[:-3]
        fpath = os.path.join(refl_dir, fname)
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        fm, _ = _parse_frontmatter(content)
        entry = ReflectionEntry(
            slug=slug, title=fm.get('title', slug), content='',
            version=int(fm.get('version', 1) or 1),
            created=fm.get('created') or '',
            modified=fm.get('modified') or '',
            patch_count=int(fm.get('patch_count', 0) or 0),
            trigger_count=int(fm.get('trigger_count', 0) or 0),
            tags=_parse_tags(fm.get('tags', [])),
            source=fm.get('source', 'unknown'),
            reason=fm.get('reason', ''),
            summary=fm.get('summary', ''),
        )
        idx[slug] = entry.to_index_record()
    _write_index(idx)
    print(f"[INFO] Rebuilt index with {len(idx)} entries")
    return idx


def _json_encoder_default(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _write_index(idx: dict) -> None:
    """写入索引（atomic write via tempfile + safe encoder）"""
    _ensure_dirs()
    tmp_path = INDEX_PATH + '.tmp'
    # 清理值：None → '', datetime → isoformat
    def _clean(v):
        if v is None:
            return ''
        if isinstance(v, datetime):
            return v.isoformat()
        if isinstance(v, (list, tuple)):
            return [_clean(x) for x in v]
        if isinstance(v, dict):
            return {kk: _clean(vv) for kk, vv in v.items()}
        return v
    cleaned = _clean(idx)
    with open(tmp_path, 'w', encoding='utf-8') as f:
        json.dump(cleaned, f, ensure_ascii=False, indent=2, default=_json_encoder_default)
        f.flush()
        os.fsync(f.fileno())
    os.rename(tmp_path, INDEX_PATH)
    # Sync parent dir
    parent_fd = os.open(os.path.dirname(INDEX_PATH), os.O_RDONLY)
    try:
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)


def _parse_frontmatter(content: str) -> tuple[dict, str]:
    """解析 Markdown 文件的 YAML frontmatter"""
    lines = content.split('\n')
    if len(lines) < 3 or lines[0].strip() != '---':
        return {}, content
    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == '---':
            end_idx = i
            break
    if end_idx is None:
        return {}, content
    import yaml  # optional, fallback to regex
    try:
        fm = yaml.safe_load('\n'.join(lines[1:end_idx])) or {}
        # Normalize: datetime → ISO string, None → ''
        for k, v in list(fm.items()):
            if isinstance(v, datetime):
                fm[k] = v.isoformat()
            elif v is None:
                fm[k] = ''
        # Normalize YAML None values (e.g. "tags:" with no value → None)
        for k, v in list(fm.items()):
            if v is None:
                fm[k] = ''
    except Exception:
        # Fallback: parse key: value lines
        fm = {}
        for line in lines[1:end_idx]:
            m = re.match(r'^(\w+):\s*(.*)$', line)
            if m:
                fm[m.group(1)] = m.group(2).strip('"\'')
    body = '\n'.join(lines[end_idx+1:]).lstrip('\n').rstrip('\n')
    return fm, body


def _fmt(v):
    """安全格式化值（datetime → ISO string, list → inline, None → '')"""
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, list):
        return '[' + ', '.join(str(x) for x in v) + ']'
    if v is None:
        return ''
    return str(v)

def _render_markdown(entry: ReflectionEntry) -> str:
    """将 ReflectionEntry 渲染为带 frontmatter 的 Markdown"""
    fm = [
        "---",
        f"slug: {_fmt(entry.slug)}",
        f"title: {_fmt(entry.title)}",
        f"version: {_fmt(entry.version)}",
        f"created: {_fmt(entry.created)}",
        f"modified: {_fmt(entry.modified)}",
        f"patch_count: {_fmt(entry.patch_count)}",
        f"trigger_count: {_fmt(entry.trigger_count)}",
        f"tags: {_fmt(entry.tags)}",
        f"source: {_fmt(entry.source)}",
        f"reason: {_fmt(entry.reason)}",
        f"summary: {_fmt(entry.summary)}",
        "---",
    ]
    content_text = _fmt(entry.content)
    if not content_text.endswith('\n'):
        content_text += '\n'  # 确保末尾有换行，避免 diff 粘连
    return '\n'.join(fm) + '\n\n' + content_text


def _generate_patch(old_content: str, new_content: str, entry: ReflectionEntry, version: int) -> str:
    """生成 unified diff patch"""
    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)
    diff = difflib.unified_diff(
        old_lines, new_lines,
        fromfile=f"{entry.slug}.md",
        tofile=f"{entry.slug}.md",
        n=3,
    )
    # Patch header: 版本信息
    ts = int(time.time())
    header = f"# v{version} | ts={ts} | source={entry.source} | reason={entry.reason or 'update'}\n"
    patch_content = header + ''.join(diff)
    return patch_content


# ─── 公开 API ────────────────────────────────────────────────────────────────

def init_pool():
    """初始化目录结构"""
    _ensure_dirs()
    if not os.path.exists(INDEX_PATH):
        _write_index({})


def create_entry(
    title: str,
    content: str,
    source: str = "reflection",
    tags: Optional[list[str]] = None,
    reason: str = "",
    summary: str = "",
) -> ReflectionEntry:
    """
    创建新 Reflection 条目（首次写入，无 patch）

    Returns:
        ReflectionEntry
    """
    init_pool()
    slug = _slugify(title)

    # 避免 slug 冲突
    base_slug = slug
    counter = 1
    while os.path.exists(_entry_path(slug)):
        slug = f"{base_slug}-{counter}"
        counter += 1

    now = datetime.now(timezone.utc).isoformat()
    entry = ReflectionEntry(
        slug=slug,
        title=title,
        content=content,
        version=1,
        created=now,
        modified=now,
        patch_count=0,
        trigger_count=0,
        tags=tags or [],
        source=source,
        reason=reason,
        summary=summary or content[:80].strip(),
    )

    # 写文件
    with open(_entry_path(slug), 'w', encoding='utf-8') as f:
        f.write(_render_markdown(entry))

    # 生成 v1.patch（初始化快照）— diff 整个文件（frontmatter+body）
    hist_dir = _history_dir(slug)
    os.makedirs(hist_dir, exist_ok=True)
    patch_file = os.path.join(hist_dir, f"v1.{int(time.time())}.patch")
    rendered = _render_markdown(entry)
    with open(patch_file, 'w', encoding='utf-8') as f:
        patch_content = f"# v1 | ts={int(time.time())} | source={source} | reason=created\n"
        patch_content += ''.join(difflib.unified_diff(
            "".splitlines(keepends=True),
            rendered.splitlines(keepends=True),
            fromfile=f"{slug}.md",
            tofile=f"{slug}.md",
            n=3,
        ))
        f.write(patch_content)

    # 更新索引
    idx = _read_index()
    idx[slug] = entry.to_index_record()
    _write_index(idx)

    return entry


def update_entry(
    slug: str,
    content: str,
    reason: str = "",
    title: Optional[str] = None,
    tags: Optional[list[str]] = None,
    summary: Optional[str] = None,
) -> Optional[ReflectionEntry]:
    """
    更新 Reflection 条目（生成 patch，可回滚）

    Returns:
        ReflectionEntry or None (if slug not found)
    """
    entry_path = _entry_path(slug)
    if not os.path.exists(entry_path):
        return None

    with open(entry_path, 'r', encoding='utf-8') as f:
        old_content = f.read()

    fm, old_body = _parse_frontmatter(old_content)
    new_body = content

    if old_body == new_body and title is None and tags is None:
        # 无变化，只更新时间
        now = datetime.now(timezone.utc).isoformat()
        entry = ReflectionEntry(
            slug=slug,
            title=fm.get('title', slug),
            content=old_body,
            version=1,
            modified=now,
        )
    else:
        # 读取现有元数据（fm 已在上面解析）
        old_version = int(fm.get('version', 1))
        new_version = old_version + 1

        now = datetime.now(timezone.utc).isoformat()
        entry = ReflectionEntry(
            slug=slug,
            title=title or fm.get('title', slug),
            content=new_body,
            version=new_version,
            created=fm.get('created') or now,
            modified=now,
            patch_count=int(fm.get('patch_count', 0)) + 1,
            trigger_count=int(fm.get('trigger_count', 0)),
            tags=tags or _parse_tags(fm.get('tags', [])),
            source=fm.get('source', 'reflection'),
            reason=reason or fm.get('reason', ''),
            summary=summary or fm.get('summary', new_body[:80].strip()),
        )

        # 生成增量 patch — diff 整个文件（frontmatter+body）
        hist_dir = _history_dir(slug)
        os.makedirs(hist_dir, exist_ok=True)
        patch_file = os.path.join(hist_dir, f"v{new_version}.{int(time.time())}.patch")
        new_rendered = _render_markdown(entry)
        patch_content = _generate_patch(old_content, new_rendered, entry, new_version)
        with open(patch_file, 'w', encoding='utf-8') as f:
            f.write(patch_content)

    # 写新内容
    with open(entry_path, 'w', encoding='utf-8') as f:
        f.write(_render_markdown(entry))

    # 更新索引
    idx = _read_index()
    if slug in idx:
        idx[slug] = entry.to_index_record()
    _write_index(idx)

    return entry


def _parse_tags(tag_str) -> list[str]:
    if isinstance(tag_str, list):
        return tag_str
    if isinstance(tag_str, str):
        # "[tag1, tag2]" 或 "tag1, tag2"
        s = tag_str.strip('[]')
        return [t.strip() for t in s.split(',') if t.strip()]
    return []


def get_entry(slug: str) -> Optional[ReflectionEntry]:
    """读取 Reflection 条目"""
    entry_path = _entry_path(slug)
    if not os.path.exists(entry_path):
        return None
    with open(entry_path, 'r', encoding='utf-8') as f:
        content = f.read()
    fm, body = _parse_frontmatter(content)
    return ReflectionEntry(
        slug=slug,
        title=fm.get('title', slug),
        content=body,
        version=int(fm.get('version', 1)),
        created=fm.get('created', ''),
        modified=fm.get('modified', ''),
        patch_count=int(fm.get('patch_count', 0)),
        trigger_count=int(fm.get('trigger_count', 0)),
        tags=_parse_tags(fm.get('tags', [])),
        source=fm.get('source', 'reflection'),
        reason=fm.get('reason', ''),
        summary=fm.get('summary', body[:80].strip()),
    )


def list_entries(source: Optional[str] = None, tag: Optional[str] = None) -> list[dict]:
    """列出所有条目（可按 source/tag 过滤）"""
    idx = _read_index()
    results = list(idx.values())
    if source:
        results = [r for r in results if r.get('source') == source]
    if tag:
        results = [r for r in results if tag in r.get('tags', [])]
    results.sort(key=lambda r: r.get('modified', ''), reverse=True)
    return results


def bump_trigger(slug: str) -> bool:
    """触发计数 +1（每次被 skill-auto-trigger 引用时调用）"""
    entry = get_entry(slug)
    if not entry:
        return False
    entry.trigger_count += 1
    # 更新磁盘文件
    entry_path = _entry_path(slug)
    with open(entry_path, 'w', encoding='utf-8') as f:
        f.write(_render_markdown(entry))
    idx = _read_index()
    idx[slug] = entry.to_index_record()
    _write_index(idx)
    return True


def rollback(slug: str, to_version: Optional[int] = None) -> Optional[ReflectionEntry]:
    """
    回滚到指定版本（或查看版本历史）

    Args:
        slug: 条目标识
        to_version: 目标版本号（None = 列出版本历史）

    Returns:
        ReflectionEntry (回滚后) 或 None
    """
    if to_version is None:
        # 列出版本历史
        return None

    entry_path = _entry_path(slug)
    if not os.path.exists(entry_path):
        return None

    # 找到所有 patch（按版本排序）
    all_patches = _history_patches(slug)
    if not all_patches:
        return None

    # 当前最新版本
    latest_version = int(re.match(r'v(\d+)\.', os.path.basename(all_patches[-1])).group(1))
    if to_version > latest_version or to_version < 1:
        return None

    if to_version == latest_version:
        print(f"[INFO] Already at v{to_version}, nothing to rollback")
        return get_entry(slug)

    # 纯 Python 重建：从 v1 逐版本正向应用 patch 到目标版本
    rebuilt = _apply_patches_to_empty(all_patches, to_version, slug)

    # 获取当前 entry 的 frontmatter 数据
    entry = get_entry(slug)
    if not entry:
        return None

    # ⚠️ 版本号永远递增，rollback 写入新版本（内容来自 to_version）
    # 这避免 rollback 后 update 产生重复版本号，导致 patch 链混乱
    new_version = latest_version + 1
    entry.content = rebuilt
    entry.version = new_version
    entry.modified = datetime.now(timezone.utc).isoformat()
    entry.reason = f"rollback to v{to_version}"
    entry.patch_count = to_version - 1  # 保留原始 patch 数量

    # 生成 rollback patch（记录从当前→回滚内容的变更）
    with open(entry_path, 'r', encoding='utf-8') as f:
        old_content = f.read()
    new_rendered = _render_markdown(entry)
    hist_dir = _history_dir(slug)
    os.makedirs(hist_dir, exist_ok=True)
    patch_file = os.path.join(hist_dir, f"v{new_version}.{int(time.time())}.patch")
    patch_content = _generate_patch(old_content, new_rendered, entry, new_version)
    with open(patch_file, 'w', encoding='utf-8') as f:
        f.write(patch_content)

    with open(entry_path, 'w', encoding='utf-8') as f:
        f.write(_render_markdown(entry))
    idx = _read_index()
    idx[slug] = entry.to_index_record()
    _write_index(idx)
    print(f"✅ Rollback to v{to_version} complete (now at v{new_version})")
    return entry


def _apply_patch_pure(current: str, patch_text: str) -> str:
    """纯 Python 应用 unified diff patch（不依赖 GNU patch）

    算法：逐 hunk 解析，将 old 区间的行替换为 new 区间。
    每个 hunk 覆盖 old_start..old_start+old_count-1 的行，
    用 +行 和 context 行替换。
    """
    lines = current.splitlines(keepends=True)
    if not current:
        lines = []

    hunks = _parse_hunks(patch_text)
    offset = 0  # 前面 hunk 导致的行数偏移

    for old_start, old_count, _ns, _nc, changes in hunks:
        # hunk 在原始文件中覆盖 old_start-1 .. old_start+old_count-2 (0-based)
        # 加上前面 hunk 的偏移
        start = (old_start - 1) + offset if old_start > 0 else 0
        start = max(0, min(start, len(lines)))

        # 构建 new 内容：context 行 + added 行
        new_lines = []
        for mark, text in changes:
            if mark in (' ', '+'):
                new_lines.append(text)

        # 替换：删掉 old_count 行，插入 new_lines
        lines[start:start + old_count] = new_lines

        # 偏移修正
        offset += len(new_lines) - old_count

    return ''.join(lines)


def _parse_hunks(patch_text: str) -> list[tuple]:
    """解析 unified diff patch 中的 hunk

    Returns: [(old_start, old_count, new_start, new_count, [(mark, text)])]
    """
    hunks = []
    in_hunk = False
    changes = []
    old_start = old_count = new_start = new_count = 0

    for line in patch_text.splitlines(keepends=True):
        if line.startswith('@@'):
            # 结束前一个 hunk
            if in_hunk and changes:
                hunks.append((old_start, old_count, new_start, new_count, changes))
                changes = []
            # 解析 @@ -old_start,old_count +new_start,new_count @@
            m = re.match(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@', line)
            if m:
                old_start = int(m.group(1))
                old_count = int(m.group(2) or '1')
                new_start = int(m.group(3))
                new_count = int(m.group(4) or '1')
            in_hunk = True
        elif in_hunk:
            if line.startswith('+') and not line.startswith('+++'):
                changes.append(('+', line[1:]))  # 保留 trailing newline
            elif line.startswith('-') and not line.startswith('---'):
                changes.append(('-', line[1:]))
            elif line.startswith(' '):
                changes.append((' ', line[1:]))
            elif not line.strip():
                # 空 context 行
                changes.append((' ', '\n'))

    # 最后一个 hunk
    if changes:
        hunks.append((old_start, old_count, new_start, new_count, changes))

    return hunks


def _apply_patches_to_empty(patches: list[str], up_to_version: int, slug: str) -> str:
    """从 v1 逐版本正向重建完整文件（frontmatter+body），返回 body 部分

    纯 Python 实现，不依赖 GNU patch。
    """
    result = ""
    for patch_path in patches:
        m = re.match(r'v(\d+)\.', os.path.basename(patch_path))
        if m and int(m.group(1)) > up_to_version:
            break
        with open(patch_path, 'r', encoding='utf-8') as f:
            patch_content = f.read()
        result = _apply_patch_pure(result, patch_content)

    # 解析 frontmatter，返回 body
    fm, body = _parse_frontmatter(result)
    return body


def diff_entry(slug: str, against_version: Optional[int] = None) -> str:
    """
    对比当前版本与指定版本（against_version=None 时对比 v1）

    Returns:
        差异文本（frontmatter + body）
    """
    entry = get_entry(slug)
    if not entry:
        return f"[ERROR] Entry '{slug}' not found"

    if against_version is None:
        against_version = 1

    # 从 patch 重建目标版本的完整文件
    patches = _history_patches(slug)
    target_body = _apply_patches_to_empty(patches, against_version, slug)

    # 生成 diff（body 部分）
    current_body = entry.content
    diff = difflib.unified_diff(
        target_body.splitlines(keepends=True),
        current_body.splitlines(keepends=True),
        fromfile=f"{slug}.md (v{against_version})",
        tofile=f"{slug}.md (current v{entry.version})",
        n=3,
    )
    return ''.join(diff)


def history(slug: str) -> list[dict]:
    """列出条目的版本历史"""
    patches = _history_patches(slug)
    records = []
    for p in patches:
        m = re.match(r'v(\d+)\.(\d+)\.patch', os.path.basename(p))
        if m:
            version = int(m.group(1))
            ts = datetime.fromtimestamp(int(m.group(2)), tz=timezone.utc).isoformat()
            records.append({
                "version": version,
                "patch_file": os.path.basename(p),
                "created": ts,
                "path": p,
            })
    return records


def search_entries(query: str, source: Optional[str] = None) -> list[dict]:
    """
    全文搜索条目（简单实现：关键词匹配标题+摘要+标签）
    """
    idx = list_entries(source=source)
    query_lower = query.lower()
    results = []
    for record in idx:
        searchable = ' '.join([
            record.get('title', ''),
            record.get('summary', ''),
            ' '.join(record.get('tags', [])),
        ]).lower()
        if query_lower in searchable:
            results.append(record)
    return results


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    """反射池 CLI 入口"""
    import argparse
    parser = argparse.ArgumentParser(description='ReflectionPool CLI')
    sub = parser.add_subparsers(dest='cmd')

    # list
    p_list = sub.add_parser('list', help='列出所有条目')
    p_list.add_argument('--source', help='按来源过滤')
    p_list.add_argument('--tag', help='按标签过滤')

    # create
    p_create = sub.add_parser('create', help='创建新条目')
    p_create.add_argument('--title', required=True)
    p_create.add_argument('--content', default='')
    p_create.add_argument('--source', default='reflection')
    p_create.add_argument('--tags', help='逗号分隔')
    p_create.add_argument('--reason', default='manual')
    p_create.add_argument('--summary', default='')
    p_create.add_argument('--file', help='从文件读取内容')

    # update
    p_update = sub.add_parser('update', help='更新条目')
    p_update.add_argument('slug')
    p_update.add_argument('--content')
    p_update.add_argument('--title')
    p_update.add_argument('--tags')
    p_update.add_argument('--reason', default='')
    p_update.add_argument('--file', help='从文件读取内容')

    # get
    p_get = sub.add_parser('get', help='读取条目')
    p_get.add_argument('slug')

    # diff
    p_diff = sub.add_parser('diff', help='对比版本')
    p_diff.add_argument('slug')
    p_diff.add_argument('--against', type=int, default=None)

    # rollback
    p_rb = sub.add_parser('rollback', help='回滚版本')
    p_rb.add_argument('slug')
    p_rb.add_argument('--to', dest='to_version', type=int, required=True)

    # history
    p_hist = sub.add_parser('history', help='查看版本历史')
    p_hist.add_argument('slug')

    # search
    p_search = sub.add_parser('search', help='搜索条目')
    p_search.add_argument('query')
    p_search.add_argument('--source')

    args = parser.parse_args()

    if args.cmd == 'list':
        entries = list_entries(source=args.source, tag=args.tag)
        print(f"ReflectionPool: {len(entries)} 条目\n")
        for e in entries:
            print(f"  [{e['source']}] {e['slug']} v{e['version']} | {e['summary'][:50]}")
            print(f"    tags={e['tags']} triggers={e['trigger_count']} modified={e['modified'][:10]}")
            print()

    elif args.cmd == 'create':
        content = args.content or ''
        if args.file:
            with open(args.file, 'r', encoding='utf-8') as f:
                content = f.read()
        tags = [t.strip() for t in args.tags.split(',')] if args.tags else []
        entry = create_entry(
            title=args.title,
            content=content,
            source=args.source,
            tags=tags,
            reason=args.reason,
            summary=args.summary or content[:80].strip(),
        )
        print(f"✅ 创建: {entry.slug} v{entry.version}")

    elif args.cmd == 'update':
        content = args.content or ''
        if args.file:
            with open(args.file, 'r', encoding='utf-8') as f:
                content = f.read()
        tags = [t.strip() for t in args.tags.split(',')] if args.tags else None
        entry = update_entry(args.slug, content=content, reason=args.reason,
                             title=args.title, tags=tags)
        if entry:
            print(f"✅ 更新: {entry.slug} → v{entry.version}")
        else:
            print(f"❌ 未找到: {args.slug}")

    elif args.cmd == 'get':
        entry = get_entry(args.slug)
        if entry:
            print(f"=== {entry.title} (v{entry.version}) ===")
            print(_render_markdown(entry))
        else:
            print(f"❌ 未找到: {args.slug}")

    elif args.cmd == 'diff':
        print(diff_entry(args.slug, against_version=args.against))

    elif args.cmd == 'rollback':
        entry = rollback(args.slug, to_version=args.to_version)
        if entry:
            print(f"✅ 回滚: {entry.slug} → v{entry.version}")
        else:
            print(f"❌ 回滚失败: {args.slug}")

    elif args.cmd == 'history':
        hist = history(args.slug)
        print(f"版本历史: {len(hist)} 个 patch\n")
        for h in hist:
            print(f"  v{h['version']} | {h['created'][:19]}Z | {h['patch_file']}")

    elif args.cmd == 'search':
        results = search_entries(args.query, source=args.source)
        print(f"搜索 '{args.query}': {len(results)} 条\n")
        for r in results:
            print(f"  [{r['source']}] {r['slug']} | {r['summary'][:60]}")

    else:
        parser.print_help()


if __name__ == '__main__':
    main()
