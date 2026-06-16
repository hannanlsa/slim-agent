"""Real-world input validation for SLIM-Agent.

Unlike the other test files, this module does NOT use mocking. It exercises
the six core modules against:

- A realistic conversational snippet (as pointer summary)
- A real public webpage (httpbin.org, which is designed for HTTP testing)
- A timeout URL (httpbin.org/delay/3 with a 1s timeout)
- Two semantically overlapping skill entries (to exercise the reducer)
- A realistic reflection entry (a postmortem-style note)

These tests may be slower than the unit tests (they hit the network), so
they are kept in their own file. They serve as a final integration check
before each release.

Run with:
    pytest tests/test_real_world.py -v

To skip them (e.g. in CI without network access):
    pytest tests/ --ignore=tests/test_real_world.py
"""

from __future__ import annotations

import socket
import time
from pathlib import Path

import pytest
from slim_agent import (
    PointerStore,
    SkillManager,
    ReflectionPool,
    SlimReducer,
    fetch_with_fallback,
    check_url,
)

# Skip the whole module if we have no internet (e.g. on a sandboxed dev box)
# Probe with a quick TCP connect to Cloudflare DNS; if DNS or routing is
# blocked, all real-world tests are skipped.
_HAS_NETWORK = True
try:
    socket.create_connection(("1.1.1.1", 53), timeout=2.0).close()
except OSError:
    _HAS_NETWORK = False

pytestmark = pytest.mark.skipif(
    not _HAS_NETWORK,
    reason="no internet access — skipping real-world tests",
)

def _httpbin_alive() -> bool:
    """Quick check if httpbin.org is currently serving. Returns True only if reachable."""
    try:
        import requests
        r = requests.get("https://httpbin.org/get", timeout=5.0)
        return r.status_code == 200
    except Exception:
        return False


requires_httpbin = pytest.mark.skipif(
    not _httpbin_alive(),
    reason="httpbin.org unreachable from this network",
)


from slim_agent import (
    PointerStore,
    SkillManager,
    ReflectionPool,
    SlimReducer,
    fetch_with_fallback,
    check_url,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def workspace(tmp_path: Path) -> dict:
    """Create a fresh workspace with a shared SQLite DB for all 4 store modules."""
    db = tmp_path / "real_world.db"
    return {
        "db": db,
        "store": PointerStore(db),
        "skills": SkillManager(db),
        "reflections": ReflectionPool(db),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 1. Pointer store with a realistic conversational snippet
# ─────────────────────────────────────────────────────────────────────────────


def test_pointer_with_realistic_conversation_snippet(workspace: dict) -> None:
    """A pointer entry should accept a real conversation snippet as summary."""
    store = workspace["store"]
    store.init_db()

    conversation = (
        "User: How do I configure the proxy for a docker build?\n"
        "Assistant: Use --build-arg HTTP_PROXY=... on the docker build command, "
        "or set it in /etc/systemd/system/docker.service.d/http-proxy.conf and "
        "restart docker."
    )

    entry = store.add_pointer(
        summary=conversation,
        primary_url="https://docs.docker.com/network/proxy/",
        tags=["docker", "proxy", "networking"],
    )

    assert entry.id is not None
    assert entry.summary == conversation
    assert "docker" in entry.tags
    assert "proxy" in entry.tags

    fetched = store.get_pointer(entry.id)
    assert fetched is not None
    assert fetched.id == entry.id
    assert fetched.summary == conversation

    # FTS5 should find it by keyword
    results = store.search_by_keyword("docker")
    assert any(p.id == entry.id for p in results), "FTS5 should index the conversation"

    # Search by tag
    by_tag = store.search_by_tag("networking")
    assert any(p.id == entry.id for p in by_tag)


# ─────────────────────────────────────────────────────────────────────────────
# 2. URL fetcher against a real public endpoint (httpbin.org)
# ─────────────────────────────────────────────────────────────────────────────


@requires_httpbin
def test_url_fetcher_real_http_endpoint(real_http) -> None:
    """fetch_with_fallback should successfully pull from a real HTTP endpoint.

    Uses httpbin.org/html which is intentionally simple, stable, and designed
    for testing. If httpbin is unreachable (e.g. firewall), this test will
    fail loudly rather than silently passing.
    """
    url = "https://httpbin.org/html"
    result = fetch_with_fallback(url, fallback_urls=[], timeout=15.0)

    assert result.ok, f"fetch should succeed against httpbin.org: {result.error}"
    assert result.status_code == 200
    assert result.url == url
    assert result.content is not None
    # httpbin/html returns an HTML page with <h1>Herman Melville</h1>
    assert len(result.content) > 100, "should return real content, not empty"
    # The HTML should be stripped of tags by _html_to_text
    assert "<html>" not in result.content.lower(), "HTML tags should be stripped"
    assert "<body>" not in result.content.lower()
    # Some text from the page should remain
    body = result.content
    assert ("Moby" in body or "Melville" in body or "Herman" in body), (
        f"expected Moby/Melville/Herman in body, got first 200 chars: {body[:200]!r}"
    )


@requires_httpbin
def test_url_fetcher_404_real_endpoint(real_http) -> None:
    """fetch_with_fallback against a 404 endpoint should report failure with status_code preserved."""
    result = fetch_with_fallback(
        "https://httpbin.org/status/404",
        fallback_urls=[],
        timeout=15.0,
    )

    assert not result.ok
    assert result.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# 3. URL health checker against a slow endpoint
# ─────────────────────────────────────────────────────────────────────────────


@requires_httpbin
def test_url_health_check_against_timeout(real_http) -> None:
    """check_url should return a non-healthy result for a slow URL with tight timeout.

    httpbin.org/delay/N waits N seconds before responding. We use delay=3
    with timeout=1.0, so it should not complete in time.
    """
    start = time.monotonic()
    result = check_url("https://httpbin.org/delay/3", timeout=1.0)
    elapsed = time.monotonic() - start

    # The check should NOT have waited the full 3 seconds
    assert elapsed < 2.5, f"check_url should respect timeout (elapsed {elapsed:.2f}s)"
    # And the result should not be alive
    assert not result.alive, f"slow URL should not be alive, got {result!r}"


# ─────────────────────────────────────────────────────────────────────────────
# 4. Two semantically overlapping skills → reducer should suggest merge
# ─────────────────────────────────────────────────────────────────────────────


def test_reducer_flags_overlapping_skills(workspace: dict) -> None:
    """Two skills with the same tags and similar summaries should be flagged."""
    sm = workspace["skills"]
    sm.init_db()

    # Realistic overlap: two skills that both handle JSON parsing, but with
    # different names. The reducer should detect the overlap and suggest a merge.
    entry1 = sm.add_skill(
        name="json-parser-stdlib",
        summary="Parse JSON strings using the Python standard library json module.",
        tags=["json", "parsing", "stdlib"],
        code_path="skills/json_parser/stdlib.py",
    )
    entry2 = sm.add_skill(
        name="json-parser-orjson",
        summary="Parse JSON strings using orjson for faster performance.",
        tags=["json", "parsing", "performance"],
        code_path="skills/json_parser/orjson.py",
    )

    # Activate both — reducer only scans ACTIVE skills
    sm.activate(entry1.id)
    sm.activate(entry2.id)

    reducer = SlimReducer(sm)  # threshold now in registry
    report = reducer.scan_skills()

    assert report.active_skill_count == 2
    # Should have at least one merge suggestion due to overlapping tags/summary
    assert len(report.suggestions) >= 1, (
        f"reducer should flag overlap, got suggestions={report.suggestions}"
    )
    # The suggestion should mention one of the overlapping skills
    suggestion = report.suggestions[0]
    assert any("json-parser" in name for name in suggestion.skill_names)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Realistic reflection entry (postmortem-style)
# ─────────────────────────────────────────────────────────────────────────────


def test_reflection_pool_realistic_postmortem(workspace: dict) -> None:
    """A real postmortem entry should be storable and queryable."""
    pool = workspace["reflections"]
    pool.init_db()

    entry = pool.add(
        error_type="false_positive_404",
        error_message=(
            "On 2026-06-14, the URL fetcher returned 200 for a 404 page because the "
            "remote server was misconfigured."
        ),
        context="url_fetcher",
        lesson_learned=(
            "Mitigation: always check Content-Type header and verify <title> tag "
            "presence, not just status_code."
        ),
    )

    assert entry.id is not None
    assert entry.error_type == "false_positive_404"
    assert "404" in entry.error_message
    assert "Content-Type" in entry.lesson_learned

    all_entries = pool.list_all()
    assert any(e.id == entry.id for e in all_entries)

    by_type = pool.query_by_error_type("false_positive_404")
    assert len(by_type) >= 1
    assert any(e.id == entry.id for e in by_type)


# ─────────────────────────────────────────────────────────────────────────────
# 6. End-to-end: store a pointer, then fetch its URL
# ─────────────────────────────────────────────────────────────────────────────


@requires_httpbin
def test_e2e_pointer_then_fetch(workspace: dict, real_http) -> None:
    """A full workflow: create a pointer, then fetch its URL to confirm it's real."""
    store = workspace["store"]
    store.init_db()

    entry = store.add_pointer(
        summary="HTTP testing endpoint returning HTML for fetch validation.",
        primary_url="https://httpbin.org/html",
        tags=["http", "test"],
    )

    assert entry.primary_url == "https://httpbin.org/html"

    # Now actually fetch it
    result = fetch_with_fallback(entry.primary_url, fallback_urls=[], timeout=15.0)
    assert result.ok, f"real fetch should succeed: {result.error}"
    assert result.status_code == 200
