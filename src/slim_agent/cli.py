"""Click CLI entry point for SLIM-Agent."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import click

from slim_agent import __version__
from slim_agent.pointer_memory.store import PointerStore
from slim_agent.reflection_pool.pool import ReflectionPool
from slim_agent.skill_manager.manager import SkillManager
from slim_agent.skill_manager.models import SkillStatus
from slim_agent.slim_reducer.reducer import SlimReducer
from slim_agent.url_fetcher.fetcher import fetch_with_fallback
from slim_agent.url_fetcher.health import batch_check


def _db_path(ctx: click.Context, param: click.Parameter, value: str | None) -> Path:
    """Resolve --db option value, falling back to parent's value.

    Click 8 does not auto-propagate root-level options to subcommands,
    so this callback walks the context chain to find an inherited value.
    """
    if value is not None:
        return Path(value)
    if ctx.parent and "db_path" in ctx.parent.params:
        return Path(ctx.parent.params["db_path"])
    return Path("slim_agent.db")


def _store(ctx: click.Context, param: click.Parameter, value: str | None) -> PointerStore:
    return PointerStore(_db_path(ctx, None, value))


def _skill_mgr(ctx: click.Context, param: click.Parameter, value: str | None) -> SkillManager:
    return SkillManager(_db_path(ctx, None, value))


def _reflect(ctx: click.Context, param: click.Parameter, value: str | None) -> ReflectionPool:
    return ReflectionPool(_db_path(ctx, None, value))


# ── shared options ─────────────────────────────────────────────────────────────


_db_opt = click.option(
    "--db",
    "db_path",
    default="slim_agent.db",
    show_default=True,
    callback=_db_path,
    help="Path to the SQLite database file.",
)


# ── init ────────────────────────────────────────────────────────────────────────


@click.group()
@click.version_option(version=__version__)
@_db_opt
def cli(db_path: Path) -> None:
    """SLIM-Agent: Self-Learning Index Memory for AI agents."""
    pass


@cli.command(name="init")
@click.pass_context
def init(ctx: click.Context) -> None:
    """Initialize all database tables."""
    db = Path(ctx.parent.params.get("db_path") or "slim_agent.db")
    ps = PointerStore(db)
    sm = SkillManager(db)
    rp = ReflectionPool(db)

    ps.init_db()
    sm.init_db()
    rp.init_db()

    ps.close()
    sm.close()
    rp.close()

    click.echo(f"Database initialized at {db}")


# ── pointer commands ────────────────────────────────────────────────────────────


@click.group()
def pointer() -> None:
    """Manage pointer memory entries."""
    pass


@pointer.command(name="add")
@click.argument("summary")
@click.argument("url")
@click.option("--tag", "-t", multiple=True, help="Tag (repeatable)")
@click.option("--fallback", "-f", multiple=True, help="Fallback URL (repeatable)")
@_db_opt
def pointer_add(
    summary: str,
    url: str,
    tag: tuple[str, ...],
    fallback: tuple[str, ...],
    db_path: Path,
) -> None:
    """Add a new pointer entry."""
    store = PointerStore(db_path)
    entry = store.add_pointer(summary=summary, primary_url=url, tags=list(tag), fallback_urls=list(fallback))
    store.close()
    click.echo(f"Added pointer #{entry.id}: {entry.summary[:60]}")


@pointer.command(name="list")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@_db_opt
def pointer_list(db_path: Path, as_json: bool) -> None:
    """List all pointer entries."""
    store = PointerStore(db_path)
    entries = store.list_all()
    store.close()

    if not entries:
        if as_json:
            click.echo("[]")
        else:
            click.echo("No pointers found.")
        return

    if as_json:
        click.echo(json.dumps([e.to_dict() for e in entries], indent=2, ensure_ascii=False))
        return

    for e in entries:
        tags_str = ", ".join(e.tags) if e.tags else "(none)"
        accessed = f", accessed {e.access_count}x" if e.access_count else ""
        click.echo(f"[{e.id}] {e.summary[:70]} | tags: {tags_str} | {e.primary_url}{accessed}")


@pointer.command(name="search")
@click.argument("keyword")
@_db_opt
def pointer_search(keyword: str, db_path: Path) -> None:
    """Full-text search pointer summaries."""
    store = PointerStore(db_path)
    entries = store.search_by_keyword(keyword)
    store.close()

    if not entries:
        click.echo(f"No results for: {keyword}")
        return

    click.echo(f"Found {len(entries)} result(s):")
    for e in entries:
        click.echo(f"[{e.id}] {e.summary[:70]} | {e.primary_url}")


@pointer.command(name="get")
@click.argument("pointer_id", type=int)
@_db_opt
def pointer_get(pointer_id: int, db_path: Path) -> None:
    """Get and display a pointer entry by id."""
    store = PointerStore(db_path)
    entry = store.get_pointer(pointer_id)
    store.close()

    if entry is None:
        click.echo(f"Pointer #{pointer_id} not found.", err=True)
        raise SystemExit(1)

    click.echo(json.dumps(entry.to_dict(), indent=2, ensure_ascii=False))


@pointer.command(name="delete")
@click.argument("pointer_id", type=int)
@_db_opt
def pointer_delete(pointer_id: int, db_path: Path) -> None:
    """Delete a pointer entry by id."""
    store = PointerStore(db_path)
    ok = store.delete_pointer(pointer_id)
    store.close()

    if ok:
        click.echo(f"Deleted pointer #{pointer_id}")
    else:
        click.echo(f"Pointer #{pointer_id} not found.", err=True)
        raise SystemExit(1)


# ── skill commands ─────────────────────────────────────────────────────────────


@click.group()
def skill() -> None:
    """Manage skill lifecycle."""
    pass


@skill.command(name="add")
@click.argument("name")
@click.option("--summary", "-s", default="", help="Short summary")
@click.option("--tag", "-t", multiple=True, help="Tag (repeatable)")
@click.option("--code-path", default="", help="Path to skill code")
@_db_opt
def skill_add(
    name: str,
    summary: str,
    tag: tuple[str, ...],
    code_path: str,
    db_path: Path,
) -> None:
    """Add a new skill (status: draft)."""
    mgr = SkillManager(db_path)
    entry = mgr.add_skill(name=name, summary=summary, tags=list(tag), code_path=code_path)
    mgr.close()
    click.echo(f"Added skill #{entry.id} '{entry.name}' (status: {entry.status.value})")


@skill.command(name="list")
@click.option("--status", "-s", type=click.Choice(["draft", "active", "deprecated", "archived"], case_sensitive=False))
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@_db_opt
def skill_list(db_path: Path, status: str | None, as_json: bool) -> None:
    """List all skills, optionally filtered by status."""
    mgr = SkillManager(db_path)
    if status:
        entries = mgr.list_by_status(SkillStatus(status))
    else:
        entries = mgr.list_all()
    mgr.close()

    if not entries:
        if as_json:
            click.echo("[]")
        else:
            click.echo("No skills found.")
        return

    if as_json:
        click.echo(json.dumps([e.to_dict() for e in entries], indent=2, ensure_ascii=False))
        return

    for e in entries:
        tags_str = ", ".join(e.tags) if e.tags else "(none)"
        click.echo(f"[{e.id}] {e.name} | v{e.version} | {e.status.value} | tags: {tags_str}")


@skill.command(name="search")
@click.argument("keyword")
@_db_opt
def skill_search(keyword: str, db_path: Path) -> None:
    """Search skills by name/summary."""
    mgr = SkillManager(db_path)
    entries = mgr.search(keyword)
    mgr.close()

    if not entries:
        click.echo(f"No skills matching: {keyword}")
        return

    for e in entries:
        click.echo(f"[{e.id}] {e.name} | v{e.version} | {e.status.value}")


@skill.command(name="activate")
@click.argument("skill_id", type=int)
@_db_opt
def skill_activate(skill_id: int, db_path: Path) -> None:
    """Activate a draft skill (draft → active)."""
    mgr = SkillManager(db_path)
    try:
        entry = mgr.activate(skill_id)
        mgr.close()
        click.echo(f"Activated skill #{entry.id} '{entry.name}'")
    except ValueError as exc:
        mgr.close()
        click.echo(str(exc), err=True)
        raise SystemExit(1)


@skill.command(name="deprecate")
@click.argument("skill_id", type=int)
@_db_opt
def skill_deprecate(skill_id: int, db_path: Path) -> None:
    """Deprecate an active skill (active → deprecated)."""
    mgr = SkillManager(db_path)
    try:
        entry = mgr.deprecate(skill_id)
        mgr.close()
        click.echo(f"Deprecated skill #{entry.id} '{entry.name}'")
    except ValueError as exc:
        mgr.close()
        click.echo(str(exc), err=True)
        raise SystemExit(1)


@skill.command(name="archive")
@click.argument("skill_id", type=int)
@_db_opt
def skill_archive(skill_id: int, db_path: Path) -> None:
    """Archive a deprecated skill (deprecated → archived)."""
    mgr = SkillManager(db_path)
    try:
        entry = mgr.archive(skill_id)
        mgr.close()
        click.echo(f"Archived skill #{entry.id} '{entry.name}'")
    except ValueError as exc:
        mgr.close()
        click.echo(str(exc), err=True)
        raise SystemExit(1)


@skill.command(name="upgrade")
@click.argument("skill_id", type=int)
@click.option("--reason", default="", help="Reason for the upgrade (recorded to ReflectionPool)")
@_db_opt
def skill_upgrade(skill_id: int, reason: str, db_path: Path) -> None:
    """Upgrade a skill (bump version patch-level)."""
    mgr = SkillManager(db_path)
    try:
        entry = mgr.upgrade(skill_id, reason=reason)
        mgr.close()
        msg = f"Upgraded skill #{entry.id} '{entry.name}' to v{entry.version}"
        if reason:
            msg += f" (reason: {reason})"
        click.echo(msg)
    except ValueError as exc:
        mgr.close()
        click.echo(str(exc), err=True)
        raise SystemExit(1)


# ── reflect commands ───────────────────────────────────────────────────────────


@click.group()
def reflect() -> None:
    """Manage reflection pool (append-only lessons)."""
    pass


@reflect.command(name="add")
@click.argument("error_type")
@click.argument("error_message")
@click.option("--context", "-c", default="", help="Error context")
@click.option("--lesson", "-l", default="", help="Lesson learned")
@click.option("--skill-id", type=int, default=None, help="Related skill id")
@_db_opt
def reflect_add(
    error_type: str,
    error_message: str,
    context: str,
    lesson: str,
    skill_id: int | None,
    db_path: Path,
) -> None:
    """Add a new reflection entry (append-only)."""
    pool = ReflectionPool(db_path)
    entry = pool.add(
        error_type=error_type,
        error_message=error_message,
        context=context,
        lesson_learned=lesson,
        related_skill_id=skill_id,
    )
    pool.close()
    click.echo(f"Added reflection #{entry.id}")


@reflect.command(name="list")
@click.option("--error-type", help="Filter by error type")
@click.option("--skill-id", type=int, help="Filter by related skill id")
@_db_opt
def reflect_list(db_path: Path, error_type: str | None, skill_id: int | None) -> None:
    """List reflection entries, optionally filtered."""
    pool = ReflectionPool(db_path)
    if error_type:
        entries = pool.query_by_error_type(error_type)
    elif skill_id is not None:
        entries = pool.query_by_skill(skill_id)
    else:
        entries = pool.list_all()
    pool.close()

    if not entries:
        click.echo("No reflections found.")
        return

    for e in entries:
        skill_ref = f" [skill #{e.related_skill_id}]" if e.related_skill_id else ""
        click.echo(f"[{e.id}] {e.error_type}{skill_ref}: {e.error_message[:60]}")
        if e.lesson_learned:
            click.echo(f"  → {e.lesson_learned[:80]}")


@reflect.command(name="search")
@click.argument("keyword")
@_db_opt
def reflect_search(keyword: str, db_path: Path) -> None:
    """Search reflections by keyword."""
    pool = ReflectionPool(db_path)
    entries = pool.search_lessons(keyword)
    pool.close()

    if not entries:
        click.echo(f"No reflections matching: {keyword}")
        return

    for e in entries:
        click.echo(f"[{e.id}] {e.error_type}: {e.lesson_learned[:80]}")


# ── slim commands ───────────────────────────────────────────────────────────────


@cli.command(name="slim")
@_db_opt
def slim(db_path: Path) -> None:
    """Scan active skills for redundancy and suggest merges (read-only)."""
    mgr = SkillManager(db_path)
    reducer = SlimReducer(mgr)
    report = reducer.scan_skills()
    mgr.close()

    click.echo(f"Scanned {report.active_skill_count} active skill(s)")
    if not report.has_overlaps:
        click.echo("No overlaps detected.")
        return

    for s in report.suggestions:
        tags_str = ", ".join(s.shared_tags) if s.shared_tags else "(none)"
        click.echo(f"\nSuggestion (score={s.overlap_score}):")
        for name in s.skill_names:
            click.echo(f"  - {name}")
        click.echo(f"  Shared tags: {tags_str}")
        click.echo(f"  Reason: {s.reason}")


# ── audit command (ponytail-review for skills) ─────────────────────────────────


@cli.command(name="audit")
@_db_opt
def audit(db_path: Path) -> None:
    """Audit skills for over-engineering patterns (read-only, advisory)."""
    import re as _re

    mgr = SkillManager(db_path)
    skills = mgr.list_all()
    mgr.close()

    if not skills:
        click.echo("No skills to audit.")
        return

    tags_count = {"delete": 0, "stdlib": 0, "native": 0, "yagni": 0, "shrink": 0}
    findings = []

    for s in skills:
        # Check for over-engineering signals
        name = s.name
        desc = s.summary or ""
        tags = s.tags or []

        # yagni: too many tags for simple skill
        if len(tags) > 10:
            findings.append(f"[yagni] skill #{s.id} '{name}' — {len(tags)} tags, likely over-classified")
            tags_count["yagni"] += 1

        # delete: empty description AND no tags
        if not desc.strip() and not tags:
            findings.append(f"[delete] skill #{s.id} '{name}' — no description, no tags")
            tags_count["delete"] += 1

        # shrink: very long description
        if len(desc) > 500:
            findings.append(f"[shrink] skill #{s.id} '{name}' — description {len(desc)} chars, consider condensing")
            tags_count["shrink"] += 1

        # stdlib: common patterns that should use builtins
        stdlib_patterns = [
            (r"request[s]?\b", "use urllib.request (stdlib)"),
            (r"simplejson", "use json (stdlib)"),
            (r"pathlib2", "use pathlib (stdlib, Python 3.4+)"),
        ]
        for pat, suggestion in stdlib_patterns:
            if _re.search(pat, desc, _re.IGNORECASE):
                findings.append(f"[stdlib] skill #{s.id} '{name}' — {suggestion}")
                tags_count["stdlib"] += 1

        # native: common patterns
        native_patterns = [
            (r"cache.*dict", "use functools.lru_cache (native)"),
            (r"enum.*constant", "use enum.Enum (native)"),
        ]
        for pat, suggestion in native_patterns:
            if _re.search(pat, desc, _re.IGNORECASE):
                findings.append(f"[native] skill #{s.id} '{name}' — {suggestion}")
                tags_count["native"] += 1

    click.echo(f"Audited {len(skills)} skill(s)\n")
    if not findings:
        click.echo("No over-engineering patterns found.")
        return

    for f in findings:
        click.echo(f)

    click.echo(f"\nSummary:")
    for tag, cnt in tags_count.items():
        if cnt:
            click.echo(f"  {tag}: {cnt}")
    click.echo(f"  Total: {sum(tags_count.values())} finding(s)")


# ── fetch command ──────────────────────────────────────────────────────────────


@cli.command(name="fetch")
@click.argument("pointer_id", type=int)
@click.option("--timeout", type=float, default=10.0, show_default=True)
@_db_opt
def fetch(pointer_id: int, timeout: float, db_path: Path) -> None:
    """Fetch content from a pointer's URL(s)."""
    store = PointerStore(db_path)
    entry = store.get_pointer(pointer_id)
    store.close()

    if entry is None:
        click.echo(f"Pointer #{pointer_id} not found.", err=True)
        raise SystemExit(1)

    result = fetch_with_fallback(entry.primary_url, entry.fallback_urls, timeout=timeout)
    if result.ok:
        click.echo(result.content[:2000])
        if len(result.content) > 2000:
            click.echo("\n... (truncated)")
    else:
        click.echo(f"Failed: {result.error}", err=True)
        raise SystemExit(1)


# ── health command ─────────────────────────────────────────────────────────────


@cli.command(name="health")
@click.option("--timeout", type=float, default=5.0, show_default=True)
@_db_opt
def health(timeout: float, db_path: Path) -> None:
    """Check liveness of all URLs stored in pointer entries."""
    store = PointerStore(db_path)
    entries = store.list_all()
    store.close()

    urls = list({e.primary_url for e in entries})
    if not urls:
        click.echo("No URLs to check.")
        return

    report = batch_check(urls, timeout=timeout)
    click.echo(f"Checked {report.total} URL(s): {report.alive_count} alive, {report.dead_count} dead")
    for r in report.results:
        status = "✓ alive" if r.alive else f"✗ dead (code={r.status_code}, err={r.error})"
        click.echo(f"  {r.url[:80]} — {status} ({r.response_time_ms:.0f}ms)")


# wire subcommands
cli.add_command(pointer)
cli.add_command(skill)
cli.add_command(reflect)


if __name__ == "__main__":
    cli()