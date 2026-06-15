# CHANGELOG

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
