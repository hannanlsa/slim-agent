"""Tests for url_fetcher module.

Uses a local HTTP server (http.server) instead of requests_mock because
fetch_content / check_url fall back to urllib when requests is not installed
(requests_mock only intercepts the requests library, not urllib).
"""

import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler

import pytest

from slim_agent.url_fetcher import (
    FetchResult,
    fetch_content,
    fetch_with_fallback,
    batch_check,
    check_url,
    HealthReport,
    HealthResult,
)


# ─── Test HTTP server fixture ────────────────────────────────────────────────


class _Handler(BaseHTTPRequestHandler):
    """Handler that serves a fixed route table defined per-test."""

    routes: dict = {}  # path -> (status_code, body)

    def log_message(self, format, *args):  # silence
        pass

    def _send(self, method: str) -> None:
        path = self.path.split("?")[0]
        # Check exact path, fall back to /<name> shorthand (e.g. /test, /missing)
        status, body = self.routes.get(path, self.routes.get("/" + path.lstrip("/"), (404, b"")))
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        self._send("GET")

    def do_HEAD(self) -> None:
        self._send("HEAD")


@pytest.fixture
def http_server():
    """Start a local HTTP server on a random port with a configurable routes table."""
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, port, _Handler
    finally:
        server.shutdown()
        thread.join(timeout=2)


def _url(port: int, path: str) -> str:
    return f"http://127.0.0.1:{port}{path}"


# ─── FetchResult unit tests ──────────────────────────────────────────────────


class TestFetchResult:
    def test_ok_property_true(self):
        result = FetchResult(
            url="http://example.com",
            content="hello",
            status_code=200,
            fetched_at=None,
        )
        assert result.ok is True

    def test_ok_property_error(self):
        result = FetchResult(
            url="http://example.com",
            content="",
            status_code=0,
            fetched_at=None,
            error="connection refused",
        )
        assert result.ok is False

    def test_ok_property_4xx(self):
        result = FetchResult(
            url="http://example.com/404",
            content="",
            status_code=404,
            fetched_at=None,
        )
        assert result.ok is False

    def test_ok_property_3xx(self):
        result = FetchResult(
            url="http://example.com/redirect",
            content="",
            status_code=301,
            fetched_at=None,
        )
        assert result.ok is True


# ─── fetch_content tests ────────────────────────────────────────────────────


class TestFetchContent:
    def test_fetch_content_success(self, http_server):
        server, port, Handler = http_server
        Handler.routes = {"/test": (200, "<p>Hello World</p>")}
        result = fetch_content(_url(port, "/test"), timeout=5.0)
        assert result.ok is True
        assert result.status_code == 200
        assert "Hello World" in result.content
        assert "<p>" not in result.content  # HTML stripped

    def test_fetch_content_404(self, http_server):
        server, port, Handler = http_server
        Handler.routes = {"/missing": (404, "")}
        result = fetch_content(_url(port, "/missing"), timeout=5.0)
        assert result.ok is False
        assert result.status_code == 404

    def test_fetch_content_timeout(self):
        # Connection refused — non-routable IP gives immediate refusal
        result = fetch_content("http://127.0.0.1:1/test", timeout=2.0)
        assert result.ok is False
        assert result.error is not None

    def test_fetch_content_no_requests_library(self, monkeypatch):
        import slim_agent.url_fetcher.fetcher as mod

        monkeypatch.setitem(mod.__dict__, "requests", None)
        result = fetch_content("http://127.0.0.1:1")
        # When requests missing, urllib path is used. Either way, ok=False.
        assert result.ok is False

    def test_fetch_content_html_entity_decode(self, http_server):
        server, port, Handler = http_server
        Handler.routes = {"/entities": (200, "<p>Hello &amp; World &mdash; &#65;</p>")}
        result = fetch_content(_url(port, "/entities"), timeout=5.0)
        assert result.ok is True
        assert "&amp;" not in result.content
        assert "&mdash;" not in result.content


# ─── fetch_with_fallback tests ──────────────────────────────────────────────


class TestFetchWithFallback:
    def test_primary_succeeds(self, http_server):
        server, port, Handler = http_server
        Handler.routes = {
            "/primary": (200, "primary content"),
            "/fallback": (200, "fallback"),
        }
        result = fetch_with_fallback(
            primary_url=_url(port, "/primary"),
            fallback_urls=[_url(port, "/fallback")],
            timeout=5.0,
        )
        assert result.ok is True
        assert "primary" in result.content

    def test_fallback_succeeds(self, http_server):
        server, port, Handler = http_server
        # /primary returns 500 (non-2xx is failure), /fallback succeeds
        Handler.routes = {
            "/primary": (500, "fail"),
            "/fallback": (200, "fallback content"),
        }
        result = fetch_with_fallback(
            primary_url=_url(port, "/primary"),
            fallback_urls=[_url(port, "/fallback")],
            timeout=5.0,
        )
        assert result.ok is True
        assert "fallback" in result.content

    def test_all_fail(self):
        # Both endpoints refused (no listener)
        result = fetch_with_fallback(
            primary_url="http://127.0.0.1:1/first",
            fallback_urls=["http://127.0.0.1:1/second"],
            timeout=2.0,
        )
        assert result.ok is False
        assert result.error is not None

    def test_empty_fallbacks(self, http_server):
        server, port, Handler = http_server
        Handler.routes = {"/only": (200, "content")}
        result = fetch_with_fallback(
            primary_url=_url(port, "/only"),
            fallback_urls=[],
            timeout=5.0,
        )
        assert result.ok is True


# ─── check_url tests ────────────────────────────────────────────────────────


class TestCheckUrl:
    def test_check_url_alive(self, http_server):
        server, port, Handler = http_server
        Handler.routes = {"/alive": (200, "")}
        r = check_url(_url(port, "/alive"), timeout=5.0)
        assert r.alive is True
        assert r.status_code == 200
        assert r.response_time_ms >= 0

    def test_check_url_5xx_not_alive(self, http_server):
        server, port, Handler = http_server
        Handler.routes = {"/error": (503, "")}
        r = check_url(_url(port, "/error"), timeout=5.0)
        assert r.alive is False
        assert r.status_code == 503

    def test_check_url_dead(self):
        # Connection refused → not alive
        r = check_url("http://127.0.0.1:1/dead", timeout=2.0)
        assert r.alive is False
        assert r.error is not None

    def test_check_url_no_requests(self, monkeypatch):
        import slim_agent.url_fetcher.health as mod

        monkeypatch.setitem(mod.__dict__, "requests", None)
        r = check_url("http://127.0.0.1:1")
        assert r.alive is False


# ─── batch_check tests ──────────────────────────────────────────────────────


class TestBatchCheck:
    def test_batch_check_all_alive(self, http_server):
        server, port, Handler = http_server
        Handler.routes = {
            "/a": (200, ""),
            "/b": (200, ""),
        }
        report = batch_check([_url(port, "/a"), _url(port, "/b")], timeout=5.0)
        assert report.total == 2
        assert report.alive_count == 2
        assert report.dead_count == 0

    def test_batch_check_mixed(self, http_server):
        server, port, Handler = http_server
        Handler.routes = {
            "/alive": (200, ""),
            # /dead returns 500 → not alive
            "/dead": (500, ""),
        }
        report = batch_check([_url(port, "/alive"), _url(port, "/dead")], timeout=5.0)
        assert report.total == 2
        assert report.alive_count == 1
        assert report.dead_count == 1

    def test_batch_check_empty(self):
        report = batch_check([], timeout=5.0)
        assert report.total == 0
        assert report.alive_count == 0


# ─── HealthReport tests ─────────────────────────────────────────────────────


class TestHealthReport:
    def test_alive_count(self, http_server):
        server, port, Handler = http_server
        Handler.routes = {
            "/a": (200, ""),
            "/b": (503, ""),  # not alive
            "/c": (200, ""),
        }
        report = batch_check(
            [_url(port, "/a"), _url(port, "/b"), _url(port, "/c")],
            timeout=5.0,
        )
        assert report.alive_count == 2
        assert report.dead_count == 1

    def test_total_property(self, http_server):
        server, port, Handler = http_server
        Handler.routes = {"/x": (200, "")}
        report = batch_check([_url(port, "/x")], timeout=5.0)
        assert report.total == 1
