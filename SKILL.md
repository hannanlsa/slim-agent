# SKILL.md — SLIM-Agent

**Project**: slim-agent · **Version**: 0.1.0 · **Python**: ≥3.10

## What It Is

SLIM-Agent = **Self-Learning Index Memory**. A Python library that gives AI agents human-brain-like memory:

1. **Pointer memory** — store knowledge as `(summary + URL + tags)`, no full text; fetch live when needed
2. **Skill lifecycle** — track skills through `draft → active → deprecated → archived`
3. **Reflection pool** — append-only log of lessons from errors/failures
4. **Slim reducer** — conservative scanner that detects redundant skills and *suggests* merges (never auto-modifies)

## Architecture

```
slim-agent/
├── src/slim_agent/
│   ├── pointer_memory/   → SQLite CRUD + FTS5 keyword search
│   ├── url_fetcher/      → HTTP fetch + HTML→text extraction + health checks
│   ├── skill_manager/    → Skill CRUD + lifecycle state machine
│   ├── reflection_pool/   → Append-only lesson log
│   ├── slim_reducer/     → Redundancy scanner (read-only suggestions)
│   └── cli.py            → Click CLI: slim init/pointer/skill/reflect/slim/fetch/health
├── tests/                → pytest test suite (tempfile for DB isolation)
├── pyproject.toml
├── SKILL.md
└── README.md
```

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| SQLite for storage | Zero-config, single-file, portable |
| Pointer = summary + URL | Avoids stale text; fetch live when needed |
| FTS5 full-text search | Fast keyword search on summaries |
| Append-only reflection | Audit trail; no update/delete |
| Slim reducer = suggest only | Human/AI must approve merges |
| `requests` + stdlib HTML parsing | Minimal deps; no heavy HTML lib required |

## CLI Quick Reference

```bash
slim init                                    # create all tables
slim pointer add "SQLite guide" "https://..." --tag db --tag python
slim pointer list
slim pointer search sqlite
slim pointer get 1
slim pointer delete 1

slim skill add my-skill --summary "does X" --tag automation
slim skill list
slim skill activate 1
slim skill deprecate 1
slim skill archive 1
slim skill upgrade 1

slim reflect add RuntimeError "division by zero" --lesson "check divisor before op"
slim reflect list
slim reflect search timeout

slim slim --threshold 0.3                    # scan for redundancies (read-only)

slim fetch 1 --timeout 10                    # fetch pointer content live
slim health                                  # check all stored URLs
```

## API Reference (key classes)

### PointerStore
```python
from slim_agent.pointer_memory import PointerStore, PointerEntry

store = PointerStore("slim_agent.db")
store.init_db()

entry = store.add_pointer(summary="...", primary_url="https://...", tags=["tag1"])
entry = store.get_pointer(1)
entries = store.search_by_keyword("sqlite")
entries = store.search_by_tag("python")
store.delete_pointer(1)
```

### SkillManager
```python
from slim_agent.skill_manager import SkillManager, SkillStatus

mgr = SkillManager("slim_agent.db")
mgr.init_db()

skill = mgr.add_skill(name="my-skill", summary="...")
skill = mgr.activate(skill.id)
skill = mgr.deprecate(skill.id)
skill = mgr.archive(skill.id)
skill = mgr.upgrade(skill.id)
```

### SlimReducer
```python
from slim_agent.slim_reducer import SlimReducer

reducer = SlimReducer(skill_manager)
report = reducer.scan_skills()   # read-only, never modifies anything
for s in report.suggestions:
    print(s.skill_names, s.overlap_score, s.reason)
```

## Dependencies

- **Runtime**: `click>=8.0.0`, `requests>=2.28.0`
- **Dev**: `pytest>=7.0.0`, `grapheme`, `unicode-width`

## CJK-Friendly

All text processing is grapheme-aware (CJK characters count as 1 grapheme, not 1 byte). Import via:

```python
from text_grapheme import count_chars, clamp_text  # optional, degrades gracefully
```

## Cross-Platform Intent & Hooks

**Important**: This skill is intentionally a *single-machine* tool. Cross-device, cross-user, cross-tool data flow is **explicitly out of scope** for v0.x. Why: that requires a desktop-class product + auth + sync engine, which a Python library cannot provide.

**What this skill DOES provide as cross-platform hooks** (so when a desktop-class product appears, it can read this data without lock-in):

1. **Standard JSON schema** — see `schema/pointer_memory.schema.json`. Any external tool/agent that wants to interoperate can read/write this format. The schema is the cross-platform contract.

2. **Pointer, not payload** — the entire philosophy is: store `summary + URL`, not full text. This means data is already portable by design (no need to migrate blobs).

3. **SQLite as the storage layer** — single-file, zero-config, easy to copy/sync/export. Any future cloud service can ingest the `.db` file or a JSON export.

4. **Reflection pool is append-only** — durable, replayable, no schema migrations needed. Future cross-platform consumers get free upgrade history.

**Intended future users of these hooks** (none of which this project will build, but it leaves the door open):

- A Raycast/Alfred-style launcher that surfaces pointer entries as quick search
- A Notion/Obsidian plugin that imports the index as a linked database
- Another agent framework (LangChain, AutoGen) reading the index as semantic search corpus
- A future "Personal AI" OS-level memory service that adopts this schema

**What this skill will NOT do** (to keep scope honest):

- ❌ Implement cloud sync
- ❌ Require user accounts / auth
- ❌ Lock data into a proprietary format
- ❌ Make network calls beyond the user's explicit `fetch` command

If a desktop-class product emerges that wants to use this data, the schema + SQLite format are the handoff point. See `README.md` → "Roadmap - Cross-Platform" for the staged plan.