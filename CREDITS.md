# CREDITS — Inspiration, Sources, and Acknowledgments

> **Why this file exists**: Open source is an *ecosystem*, not a tree. Ideas don't fall from the sky — they come from people, projects, papers, and conversations. Every line in `slim-agent` traces back to something that came before. This file is a transparent record of that lineage, so that:
>
> 1. **Future contributors** can trace where ideas came from and find their way back to original sources.
> 2. **Other projects** that build on this one can give credit upstream.
> 3. **The chain of ideas stays auditable** — preventing the silent misattribution that plagues AI work.
>
> If you fork, extend, or learn from slim-agent, please keep this lineage intact and add your own credits to whatever you build next.

---

## Direct Code / Library Dependencies

These are the libraries `slim-agent` imports and ships alongside. They run inside this project.

| Project | Author / Maintainer | License | What we use | File / Role |
|---------|---------------------|---------|-------------|-------------|
| [grapheme](https://github.com/alvinlindstam/grapheme) | Alvin Lindstam | MIT | CJK-aware grapheme counting | Text handling |
| [unicode-width](https://github.com/jquast/unicode-width) | Jason Quast | MIT | Terminal cell width | Display formatting |
| [click](https://github.com/pallets/click) | Pallets team | BSD-3 | CLI framework | `cli.py` |
| [requests](https://github.com/psf/requests) | Kenneth Reitz et al. | Apache-2.0 | HTTP client | `url_fetcher/fetcher.py` |
| [pytest](https://github.com/pytest-dev/pytest) | Holger Krekel et al. | MIT | Test framework | `tests/` |
| [requests-mock](https://github.com/jamielennox/requests-mock) | Jamie Lennox | Apache-2.0 | HTTP mocking in tests | `tests/` |
| [SQLite](https://sqlite.org) | D. Richard Hipp | Public Domain | Database | `pointer_memory`, `skill_manager`, `reflection_pool` |
| [Python FTS5](https://www.sqlite.org/fts5.html) | SQLite team | Public Domain | Full-text search | `pointer_memory` |

---

## Design Inspiration — Major Influences

These are the projects, people, and papers that shaped how `slim-agent` thinks about its core problems. None of their code is copied. **Ideas, patterns, and stances are borrowed; implementation is original.**

### OpenHuman — tinyhumansai/openhuman

**Borrowed ideas** (in spirit, not code):
- **Pointer-memory philosophy** — "store the conclusion + the URL, fetch live when needed." This is the **core architectural decision** of slim-agent.
- **CJK-aware text processing** — grapheme-based counting rather than byte-based slicing.
- **Atomic write pattern** — tempfile + fsync + rename to avoid corruption.
- **Sandbox philosophy** — deny by default, allow narrowly.
- **Three-layer rule loading** — builtin > user > project.

**License**: GPL-3.0. (We do NOT copy code; the philosophy is reused with reimplementation, deliberately avoiding GPL contamination.)

### ARS — anthropic-experimental/academic-research-skills

**Borrowed ideas**:
- **Material Passport pattern** — append-only hash-chained checkpoints for resumable work.
- **Anti-Patterns 25-word list** — common AI-speak words to avoid.
- **Pre-commitment prompts** — declare success criteria before doing the work.
- **5-type Citation Hallucination taxonomy** — for future citation auditing extensions.
- **Checkpoint FULL/SLIM/MANDATORY** — three-level reporting cadence.

**License**: CC BY-NC 4.0. (We borrow *concepts* only, not prompt text, due to license.)

### Superpowers — obra/superpowers

**Borrowed ideas**:
- **Feedback Loop First** — debugging starts with building a fast, deterministic pass/fail loop, not guessing.
- **Caveman mode** — extreme token compression for repetitive communication.
- **Two-stage review** — scope/spec compliance first, quality second; never the reverse.
- **Handoff template** — compress session state for the next session.
- **Anti-hallucination evidence mandates** — every claim must have a verification path.

**License**: MIT. (We borrow ideas with reimplementation.)

### mattpocock/skills

**Borrowed ideas**:
- **CONTEXT.md domain language** — keep project glossary in a single file, update inline.
- **write-a-skill specification** — SKILL.md ≤ 100 lines, description ≤ 1024 chars, third-person, "Use when..." trigger.
- **Skill categorization** — engineering / productivity / personal buckets.

**License**: MIT. (We borrow ideas with reimplementation.)

### Everything Claude Code (ECC) — affaan-m/ecc

**Borrowed ideas**:
- **agent-sort philosophy** — DAILY (always-on) vs LIBRARY (on-demand) vs NEVER buckets. (We adapt this as a runtime bucket strategy, not a static categorization.)
- **context-budget token estimation** — words×1.3 / chars÷4 heuristic.
- **MCP→CLI lazy-load stance** — call out to tools only when needed, never import a server.
- **Skill description discipline** — concise, trigger-rich, no scope creep in the description.

**License**: MIT. (We borrow ideas with reimplementation.)

### agentmemory — rohitg00/agentmemory

**Borrowed ideas**:
- **Persistent memory across sessions** — local-first storage of meaningful facts.
- **Semantic search as a thin layer** — over a simple CRUD store.
- **JSON-RPC over stdio** — a clean agent↔tool interface.

**License**: MIT. (We borrow ideas; we deliberately do NOT use the agentmemory MCP server in slim-agent, to keep the project lightweight and dependency-free.)

### OpenClaw / QClaw

**Borrowed ideas** (from the author's own previous work):
- **Skill registry + auto-trigger pattern** — the trigger_map / dispatcher concept.
- **`list_always_on()` baseline** — a small set of skills that fire on every task.
- **TDD red-green-refactor generalized to non-code tasks** — define success criteria, run, verify, ship.

**License**: Project-internal. (Same author, so this is the upstream of `slim-agent`'s own skill ecosystem.)

---

## Conceptual / Philosophical Sources

These are ideas that don't map to specific files but shape the project's stance.

| Source | Idea borrowed |
|--------|---------------|
| **Human brain memory research** (general cognitive science) | The pointer-vs-payload distinction comes from how humans remember conclusions + where to find them, not full text. |
| **Linus's "good taste"** (kernel development philosophy) | Eliminate special cases by redesigning data structures, not by adding branches. Drives slim-agent's conservative reducer stance. |
| **Hyrum's Law** (Hyrum Wright) | All observable behaviors of a system will be depended on by somebody. Drives the schema-stability commitment in `schema/pointer_memory.schema.json`. |
| **Postel's Law** (RFC 793) | "Be conservative in what you do, be liberal in what you accept." Drives the schema's `additionalProperties: true` for the `metadata` field. |
| **The "explicit settings" stance** (Twelve-Factor App) | No hidden state, no implicit config. Drives SQLite-as-a-single-file + JSON export. |
| **Karpathy's "think before coding" + surgical changes + simplicity first** | Cited in the project's development workflow: define the spec, make the minimal change, verify with tests. |

---

## Conversation / Discussion Sources

| Conversation | Date | What was discussed |
|--------------|------|-------------------|
| **和Gemini的问答.docx** | 2026-06-15 | The brainstorming conversation that gave rise to the SLIM-Agent concept (Self-Learning Index Memory). The conversation also produced the **four evolution pillars** (锁定进化方向) that now permanently guide this project: (1) SimHash fingerprint + PointerStore, (2) Local minimize + internet pointers, (3) Skill iteration, (4) Slim reducer. These four pillars are now codified in README.md and SKILL.md as the binding contract for the project's direction. |
| **OpenClaw / QClaw session logs** | 2026-05-23 onward | Architectural decisions on skill ecosystem, dispatcher patterns, agent-sort philosophy, and the "Copilot Not Pilot" stance. |

---

## Author's Note (2026-06-15)

This project was built in one afternoon by a single author (潘笑) using:
- A sub-agent (slim-agent-generator) to write the initial code
- A code reviewer agent to fix 3 bugs after the first round of tests
- Open-source tools and ideas from the projects credited above
- The author's own previous work in the OpenClaw / QClaw project

The slim-agent's value is **not** in any single clever implementation. It is in the **specific combination of borrowed ideas**:
- Pointers-not-payload (OpenHuman)
- Lifecycle state machine (skill_manager)
- Append-only reflection (ARS-inspired)
- Conservative reducer (own stance)
- Cross-platform schema as a hook, not a sync protocol (own design)

If you find this combination useful, build on it. If you find a better combination, replace it. Either way, **leave a credit trail**.

---

## How to Add Your Credit

If you fork, extend, or learn from slim-agent and produce a derivative work, please add a `CREDITS.md` (or equivalent) to your project with:

1. **Your direct code/library deps** (with licenses).
2. **Major design influences** (with links, even if you didn't copy code).
3. **Conceptual sources** (people, papers, ideas).
4. **Conversation sources** (if discussions shaped the design).
5. **Author's note** (how the work came together).

The chain of ideas stays auditable. The ecosystem gets healthier. The next person learns faster.
