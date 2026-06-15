# SLIM-Agent

**Self-Learning Index Memory for AI agents**

[![Python ≥3.10](https://img.shields.io/badge/python-%E2%89%A53.10-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

---

## What Is SLIM-Agent?

SLIM-Agent gives AI agents **human-brain-like memory**. Instead of storing full text (which goes stale and burns token budget), it stores **pointer-style knowledge**: a short summary, one or more URLs, and tags. The agent fetches the live content when it needs it.

It also manages:

- **Skill lifecycle** — skills evolve from `draft` → `active` → `deprecated` → `archived`
- **Reflection pool** — an append-only log of lessons learned from errors and failures
- **Slim reducer** — a conservative scanner that detects redundant skills and *suggests* merges (it never auto-modifies anything; human or AI must approve)

---

## Why It Exists

AI agents accumulate knowledge over time. Two problems arise:

1. **Knowledge bloat** — storing full text for every fact burns context window and goes stale
2. **Skill drift** — skills proliferate with overlapping functionality, no one knows what's current

SLIM-Agent solves both:
- **Pointers instead of text** — summary + URL; fetch live when needed
- **Skill lifecycle** — explicit states prevent zombie skills from cluttering the system
- **Self-slimming** — the reducer finds overlaps and suggests consolidation

---

## Installation

```bash
# Install from source
pip install -e .

# With dev dependencies (for running tests)
pip install -e ".[dev]"
```

Or install the package directly from the repo:

```bash
pip install git+https://github.com/your-org/slim-agent.git
```

---

## Quick Start

```bash
# 1. Initialize the database (creates all tables)
slim init

# 2. Add a pointer
slim pointer add "SQLite FTS5 tutorial" "https://www.sqlite.org/fts5.html" --tag sqlite --tag search

# 3. List all pointers
slim pointer list

# 4. Search pointers
slim pointer search sqlite

# 5. Add a skill
slim skill add my-search-skill --summary "Full-text search using SQLite FTS5" --tag search

# 6. Activate the skill
slim skill activate 1

# 7. Add a reflection (lesson learned from an error)
slim reflect add TimeoutError "request timed out after 30s" \
  --lesson "always set a timeout on HTTP requests" --skill-id 1

# 8. Scan for skill redundancy
slim slim --threshold 0.3

# 9. Fetch live content from a pointer's URL
slim fetch 1 --timeout 10

# 10. Check health of all stored URLs
slim health
```

---

## Architecture

```
slim-agent/
├── src/slim_agent/
│   ├── pointer_memory/       # SQLite CRUD + FTS5 full-text search
│   │   ├── models.py         # PointerEntry dataclass
│   │   └── store.py          # PointerStore: add/get/search/delete
│   ├── url_fetcher/          # Real-time HTTP fetching
│   │   ├── fetcher.py        # fetch_content(), fetch_with_fallback()
│   │   └── health.py         # check_url(), batch_check()
│   ├── skill_manager/        # Skill lifecycle state machine
│   │   ├── models.py         # SkillEntry, SkillStatus enum
│   │   └── manager.py        # SkillManager: CRUD + transitions
│   ├── reflection_pool/      # Append-only lesson log
│   │   ├── models.py         # ReflectionEntry dataclass
│   │   └── pool.py           # ReflectionPool: add/query/search
│   ├── slim_reducer/         # Conservative redundancy scanner
│   │   ├── models.py         # MergeSuggestion, RedundancyReport
│   │   └── reducer.py        # SlimReducer.scan_skills()
│   └── cli.py                # Click CLI (slim init/pointer/skill/reflect/slim/fetch/health)
├── tests/                    # pytest test suite
├── pyproject.toml
├── SKILL.md                   # For AI agents
└── README.md
```

---

## Data Storage

All data lives in a single SQLite file (`slim_agent.db` by default).

### Tables

| Table | Description |
|-------|-------------|
| `pointers` | Pointer entries (summary, tags JSON, primary_url, fallback_urls JSON, access_count) |
| `pointers_fts` | FTS5 virtual table for full-text search on summaries |
| `skills` | Skill entries with lifecycle status, version, parent_skill_id |
| `reflections` | Append-only reflection entries (error_type, lesson_learned, context) |

---

## Skill Lifecycle

```
  draft ──► active ──► deprecated ──► archived
```

- `draft` — newly created, not yet active
- `active` — in use, current version
- `deprecated` — superseded but not removed yet
- `archived` — fully retired

Transitions are enforced: you cannot skip states (e.g., `draft → archived` is invalid).

---

## API Reference

### PointerStore

```python
from slim_agent.pointer_memory import PointerStore, PointerEntry

store = PointerStore("slim_agent.db")
store.init_db()

# Add
entry = store.add_pointer(
    summary="SQLite FTS5 tutorial",
    primary_url="https://sqlite.org/fts5.html",
    tags=["sqlite", "search"],
    fallback_urls=["https://mirror.example.com/fts5.html"],
)

# Get (increments access_count)
entry = store.get_pointer(1)

# Search
results = store.search_by_keyword("sqlite")
results = store.search_by_tag("search")

# List
all_entries = store.list_all()

# Delete
store.delete_pointer(1)
```

### SkillManager

```python
from slim_agent.skill_manager import SkillManager, SkillStatus

mgr = SkillManager("slim_agent.db")
mgr.init_db()

# Add (starts as draft)
skill = mgr.add_skill(name="my-skill", summary="...", tags=["tag1"])

# Lifecycle transitions
skill = mgr.activate(skill.id)     # draft → active
skill = mgr.deprecate(skill.id)   # active → deprecated
skill = mgr.archive(skill.id)     # deprecated → archived
skill = mgr.upgrade(skill.id)     # bump version + link to self as parent

# Query
drafts = mgr.list_by_status(SkillStatus.DRAFT)
active = mgr.list_by_status(SkillStatus.ACTIVE)
found = mgr.search("keyword")
```

### ReflectionPool

```python
from slim_agent.reflection_pool import ReflectionPool

pool = ReflectionPool("slim_agent.db")
pool.init_db()

# Append (no update, no delete)
entry = pool.add(
    error_type="TimeoutError",
    error_message="request timed out",
    context="calling fetch_content() without timeout",
    lesson_learned="always set a timeout",
    related_skill_id=1,
)

# Query
all_refs = pool.list_all()
by_type = pool.query_by_error_type("TimeoutError")
by_skill = pool.query_by_skill(1)
found = pool.search_lessons("timeout")
```

### SlimReducer

```python
from slim_agent.slim_reducer import SlimReducer

reducer = SlimReducer(skill_manager, threshold=0.3)
report = reducer.scan_skills()   # read-only, never modifies anything

print(f"Scanned {report.active_skill_count} skills")
for s in report.suggestions:
    print(f"Merges suggested: {s.skill_names}")
    print(f"  Score: {s.overlap_score}, Reason: {s.reason}")
```

### URL Fetcher

```python
from slim_agent.url_fetcher import fetch_content, fetch_with_fallback

# Single URL
result = fetch_content("https://example.com", timeout=10.0)
if result.ok:
    print(result.content)

# With fallbacks
result = fetch_with_fallback(
    primary_url="https://primary.example.com",
    fallback_urls=["https://fallback.example.com"],
    timeout=10.0,
)
```

### Health Checker

```python
from slim_agent.url_fetcher import batch_check, check_url

# Single URL
r = check_url("https://example.com")
print(f"Alive: {r.alive}, Response time: {r.response_time_ms}ms")

# Batch
report = batch_check(["https://a.com", "https://b.com"], timeout=5.0)
print(f"{report.alive_count}/{report.total} URLs alive")
```

---

## Running Tests

```bash
pip install -e ".[dev]"
python -m pytest tests/ -v
```

All unit tests use temporary files/databases for isolation — no state leaks between tests.

### Real-world integration tests

`tests/test_real_world.py` contains integration tests that hit **real public
endpoints** (httpbin.org). These are auto-skipped if:
- No internet is available (probes `1.1.1.1:53`)
- httpbin.org is unreachable (probes `/get`)

To run only the real-world tests:
```bash
python -m pytest tests/test_real_world.py -v
```

To skip them in CI (e.g. if your build server has no internet):
```bash
python -m pytest tests/ --ignore=tests/test_real_world.py
```

---

## CJK-Friendly Text Handling

All text processing is grapheme-aware. CJK characters and emoji are counted as 1 grapheme (not 1 byte). The library degrades gracefully when `grapheme` is not installed.

```python
# Optional: install for full CJK support
pip install grapheme unicode-width
```

---

## License

MIT License. See [LICENSE](LICENSE) for details.

---

## Credits & Acknowledgments

This project stands on the shoulders of others. See [CREDITS.md](CREDITS.md) for the full lineage — direct dependencies, design inspirations (OpenHuman, ARS, Superpowers, mattpocock/skills, ECC, agentmemory, OpenClaw), conceptual sources, and conversation sources. **The chain of ideas stays auditable so that future contributors can trace where every design decision came from.**

---

## Roadmap — Cross-Platform

**Stance**: This project explicitly scopes itself to **single-machine, local-first**. Cross-device, cross-user, cross-tool data flow is deferred to a future product layer that this Python library alone cannot provide.

The reasoning: real cross-platform requires auth, sync engines, conflict resolution, devices, and UX — a desktop-class product concern, not a library concern. Aiming for it now would over-build and lock users in.

### v0.x (now) — Single-machine foundation

- ✅ SQLite storage, single file
- ✅ Pointer = summary + URL (no payload)
- ✅ JSON export of pointer entries
- ✅ Standard JSON schema (`schema/pointer_memory.schema.json`) ← **cross-platform hook**

**What this version provides as cross-platform hooks:**

1. **Schema** (`schema/pointer_memory.schema.json`) — any external tool/agent can read/write pointer entries in this standardized format. The schema is intentionally the cross-platform *contract*.
2. **Storage is portable** — a single `.db` file or its JSON export. Easy to copy, sync, ingest.
3. **Pointers, not payloads** — full content stays at URLs. No blob migration cost.
4. **Append-only reflections** — replayable, no schema migrations needed by future consumers.

**What v0.x does NOT do (intentional):**

- ❌ Cloud sync
- ❌ User accounts / auth
- ❌ Proprietary data formats
- ❌ Network calls beyond explicit `fetch` command

### v1.x (when?) — Data portability layer

**Trigger**: A second consumer (CLI launcher, Notion plugin, another agent) wants to ingest the index.

- Provide `slim export` / `slim import` for portable JSON bundles
- Provide reference readers in 2-3 popular languages (JS, Rust) that consume `pointer_memory.schema.json`
- Document "interop recipes" in this README

**Out of scope**: still no cloud, no auth, no multi-user.

### v2.x (much later) — Cross-device sync

**Trigger**: A desktop-class / category-defining product emerges (think Raycast, Notion, Things) that has UX/auth/devices/conflict-resolution layers. At that point, the v0.x schema is the stable interface that the product can adopt.

- That product can ingest a user's v0.x SQLite file or JSON export
- The schema stays unchanged — users keep their data
- A v0.x user upgrading to v2.x needs only to point the new product at their existing `slim_agent.db` file

### What this means for users today

- ✅ Your data is yours, in a portable schema
- ✅ Any future "Personal AI" service can read what you wrote
- ✅ Lock-in is impossible (open source + open format)
- ⏸ Wait for a real cross-platform product before expecting sync

The hook is in place. The data is future-proof. The actual cross-platform experience waits for a product that earns it.