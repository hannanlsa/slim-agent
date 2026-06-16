# CHANGELOG

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.8] - 2026-06-16

### Added
- `slim_reducer/bm25.py`: BM25 TF/IDF keyword matching signal (借鉴 Qdrant lib/bm25/)
- `slim_reducer/rrf.py`: RRF Reciprocal Rank Fusion scorer (借鉴 Qdrant lib/collection/)
- 8 new tests (4 BM25 + 4 RRF), all passing

### Changed
- `slim_reducer/reducer.py`: 预建 BM25 index + RRF 融合替代 max(score)
- `slim_reducer/reducer.py`: BM25 作为第 4 信号 (threshold=0.15, weight=1.5)
- `reducer.py` reason 字段标注 RRF 分数

### Docs
- README.md: 新增 🔒 Evolution Direction 章节 (四大 pillars 锁定)
- SKILL.md: 同上 🔒 Evolution Direction
- CREDITS.md: 补充和Gemini对话产出四大 pillars 的来源
- 版本号: 0.1.6 → 0.1.8

## [0.1.7] - 2026-06-16

### Added
- `slim_reducer/registry.py`: SignalRegistry (动态信号注册/禁用/求值)
- `slim_reducer/loop_detector.py`: LoopDetector (渐进式循环检测 nudge)
- `models.py`: `MergeSuggestion.severity` 字段 (info/warning/critical)
- `models.py`: `RedundancyReport.active_skill_count` 字段

### Changed
- `reducer.py`: 硬编码信号 → SignalRegistry 动态信号
- `scan_skills()`: 渐进式 severity 分级替代单一阈值
- 版本号: 0.1.6 → 0.1.7

## [0.1.6] - 2026-06-16

### Added
- OpenClaw skill packaging (`~/.qclaw/skills/slim-agent/`):
  - `SKILL.md`: trigger words, anti-triggers, companion skills, Python API reference
  - `__init__.py`: `is_available()`, `version()`, `auto_detect()`, `self_test()`
- CREDITS.md documenting cross-repo idea lineage

### Changed
- PyPI production release (v0.1.5 → v0.1.6)

## [0.1.1] - 2026-06-15

### Added
- Top-level re-exports in `slim_agent/__init__.py` so users can write
  `from slim_agent import PointerStore` instead of the longer
  `from slim_agent.pointer_memory.store import PointerStore`.
  Sub-module paths still work and remain canonical.
- `[project.urls]` in `pyproject.toml` for Homepage, Repository, Issues,
  Changelog, Credits — these surface on the PyPI project page.
- `[project.keywords]` (ai, agent, memory, rag, pointer, index, self-learning)
  for better PyPI discoverability.
- Maintainers field with author email.
- `[tool.pytest.ini_options]` for predictable test discovery.
- `build` and `hatchling` in `[project.optional-dependencies].dev` so
  contributors can `pip install -e ".[dev]"` and immediately build sdist/wheel.
- New classifiers: `Operating System :: OS Independent`,
  `Programming Language :: Python :: 3 :: Only`,
  `Intended Audience :: Science/Research`,
  `Topic :: Scientific/Engineering :: Artificial Intelligence`,
  `Typing :: Typed`.
- Verified `python -m build --sdist --wheel` produces installable artifacts.
- Verified wheel installs cleanly in a fresh venv and `slim --version` reports 0.1.1.

### Fixed
- `cli --version` previously reported 0.1.0 even after code changes — now
  reads from `slim_agent.__version__` which is bumped to 0.1.1.
- Build exclude list was missing `*.egg-info`, `__pycache__`, `*.pyc`,
  `.pytest_cache`, `build/`, `dist/` — now properly excluded from sdist.

### Verified
- `pip install -e .` works.
- `pip install dist/slim_agent-0.1.1-py3-none-any.whl` works in fresh venv.
- `slim --version` → `slim, version 0.1.1`.
- `slim --help` lists all 7 subcommands.
- All 85 tests pass (`pytest tests/`).
- Top-level imports work: `from slim_agent import PointerStore, SkillManager, SlimReducer`.

## [0.1.0] - 2026-06-15

### Added
- Initial release.
- 6 core modules: `pointer_memory`, `skill_manager`, `reflection_pool`,
  `slim_reducer`, `url_fetcher`, `cli`.
- SQLite storage with FTS5 full-text search on pointer summaries.
- Skill lifecycle state machine: `draft → active → deprecated → archived`.
- Append-only reflection pool.
- Conservative slim reducer (read-only suggestions).
- URL fetcher with HTTP→HTML→text pipeline and fallback URLs.
- Click CLI with subcommands: `init`, `pointer`, `skill`, `reflect`, `slim`,
  `fetch`, `health`.
- 85-test pytest suite with tempfile-isolated DBs.
- CREDITS.md documenting design lineage.
- SKILL.md for AI agent consumers.
- Schema: `schema/pointer_memory.schema.json`.
- Cross-platform hooks (see SKILL.md § "Cross-Platform Intent & Hooks").
- See [CREDITS.md](CREDITS.md) for design inspiration sources.

[0.1.1]: https://github.com/hannanlsa/slim-agent/compare/0.1.0...0.1.1
[0.1.0]: https://github.com/hannanlsa/slim-agent/releases/tag/0.1.0


## [0.1.2] - 2026-06-15

### Added
- `tests/test_real_world.py` — 7 integration tests that exercise the 6 core
  modules against real-world inputs (no mocking):
  - Pointer with a realistic conversational snippet (Docker proxy discussion)
  - URL fetcher against httpbin.org/html (real HTTP 200 + HTML stripping)
  - URL fetcher against httpbin.org/status/404 (real 404 propagation)
  - Health checker against httpbin.org/delay/3 with 1s timeout (timeout enforcement)
  - Reducer with two semantically overlapping skills (suggests merge)
  - Reflection pool with a real postmortem-style entry
  - End-to-end: store pointer, then fetch its URL
- `real_http` fixture in `tests/conftest.py` — temporarily disables the
  session-level requests-mock for a single test, then re-enables it.
- `_httpbin_alive()` helper + `@requires_httpbin` marker in test_real_world.py
  to skip tests when httpbin.org is unreachable.
- `pytestmark = skipif(not _HAS_NETWORK)` at module level — the entire
  real-world suite is skipped if no internet is available (probes 1.1.1.1:53).
- README §"Running Tests" now documents how to run or skip real-world tests.

### Fixed
- `PointerStore.add_pointer()` parameter is `primary_url`, not `url`.
- `fetch_with_fallback()` requires `fallback_urls` as second positional arg.
- `SlimReducer` only scans ACTIVE skills — `add_skill` defaults to DRAFT,
  tests now call `sm.activate(skill_id)` explicitly.
- `MergeSuggestion` exposes `skill_ids` (list[int]) and `skill_names` (list[str]),
  not `skill_a` / `skill_b`.
- `ReflectionPool.add()` signature is `(error_type, error_message, context, lesson_learned, related_skill_id)`,
  not `(content=...)`.

### Verified
- 88/88 unit tests pass.
- 4 real-world tests auto-skip when httpbin is unreachable.
- `python -m build --sdist --wheel` produces installable artifacts.

[0.1.2]: https://github.com/hannanlsa/slim-agent/compare/0.1.1...0.1.2

## [0.1.5] - 2026-06-16

### Added
- SimHash-based summary similarity signal in `SlimReducer` for CJK + paraphrase robustness
- `simhash` module: character 4-gram → 64-bit BLAKE2b → Hamming distance similarity
- New tests: `tests/test_simhash.py` (15 tests), CJK + paraphrase coverage in `test_slim_reducer.py`
- Conservative `simhash_threshold=0.65` (tunable per-call)

### Changed
- `SlimReducer.scan_skills()` now combines 3 signals (tag Jaccard, word Jaccard, SimHash) and reports each fired signal in `reason`
- Pre-computes SimHash fingerprints once per scan (avoids O(N²) recomputation)

### Fixed
- (none)

[0.1.4] skipped — CLI bug fixes were rolled into the v0.1.5 testing flow
