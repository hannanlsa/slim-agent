"""Tests for url_fetcher module."""

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


class TestFetchResult:
    def test_ok_property_true(self):
        result = FetchResult(
            url="https://example.com",
            content="hello",
            status_code=200,
            fetched_at=None,
        )
        assert result.ok is True

    def test_ok_property_error(self):
        result = FetchResult(
            url="https://example.com",
            content="",
            status_code=0,
            fetched_at=None,
            error="connection refused",
        )
        assert result.ok is False

    def test_ok_property_4xx(self):
        result = FetchResult(
            url="https://example.com/404",
            content="",
            status_code=404,
            fetched_at=None,
        )
        assert result.ok is False

    def test_ok_property_3xx(self):
        result = FetchResult(
            url="https://example.com/redirect",
            content="",
            status_code=301,
            fetched_at=None,
        )
        assert result.ok is True


class TestFetchContent:
    def test_fetch_content_success(self):
        from requests_mock import Mocker

        with Mocker() as rm:
            rm.get("https://example.com/test", text="<p>Hello World</p>", status_code=200)
            result = fetch_content("https://example.com/test", timeout=5.0)
            assert result.ok is True
            assert result.status_code == 200
            assert "Hello World" in result.content
            assert "<p>" not in result.content  # HTML stripped

    def test_fetch_content_404(self):
        from requests_mock import Mocker

        with Mocker() as rm:
            rm.get("https://example.com/missing", status_code=404)
            result = fetch_content("https://example.com/missing", timeout=5.0)
            assert result.ok is False
            assert result.status_code == 404

    def test_fetch_content_timeout(self):
        from requests_mock import Mocker

        with Mocker() as rm:
            rm.get("https://example.com/slow", exc=Exception("timeout"))
            result = fetch_content("https://example.com/slow", timeout=5.0)
            assert result.ok is False
            assert result.error is not None

    def test_fetch_content_no_requests_library(self, monkeypatch):
        import slim_agent.url_fetcher.fetcher as mod

        monkeypatch.setitem(mod.__dict__, "requests", None)
        result = fetch_content("https://example.com")
        assert result.error == "requests library not installed"
        assert result.ok is False

    def test_fetch_content_html_entity_decode(self):
        from requests_mock import Mocker

        html = "<p>Hello &amp; World &mdash; &#65;</p>"
        with Mocker() as rm:
            rm.get("https://example.com/entities", text=html, status_code=200)
            result = fetch_content("https://example.com/entities", timeout=5.0)
            assert result.ok is True
            assert "&amp;" not in result.content
            assert "&mdash;" not in result.content


class TestFetchWithFallback:
    def test_primary_succeeds(self):
        from requests_mock import Mocker

        with Mocker() as rm:
            rm.get("https://primary.example.com", text="primary content", status_code=200)
            rm.get("https://fallback.example.com", text="fallback", status_code=200)
            result = fetch_with_fallback(
                primary_url="https://primary.example.com",
                fallback_urls=["https://fallback.example.com"],
                timeout=5.0,
            )
            assert result.ok is True
            assert "primary" in result.content

    def test_fallback_succeeds(self):
        from requests_mock import Mocker

        with Mocker() as rm:
            rm.get("https://primary.invalid", exc=Exception("fail"))
            rm.get("https://fallback.example.com", text="fallback content", status_code=200)
            result = fetch_with_fallback(
                primary_url="https://primary.invalid",
                fallback_urls=["https://fallback.example.com"],
                timeout=5.0,
            )
            assert result.ok is True
            assert "fallback" in result.content

    def test_all_fail(self):
        from requests_mock import Mocker

        with Mocker() as rm:
            rm.get("https://first.invalid", exc=Exception("fail"))
            rm.get("https://second.invalid", exc=Exception("fail"))
            result = fetch_with_fallback(
                primary_url="https://first.invalid",
                fallback_urls=["https://second.invalid"],
                timeout=5.0,
            )
            assert result.ok is False
            assert result.error is not None

    def test_empty_fallbacks(self):
        from requests_mock import Mocker

        with Mocker() as rm:
            rm.get("https://example.com", text="content", status_code=200)
            result = fetch_with_fallback(
                primary_url="https://example.com",
                fallback_urls=[],
                timeout=5.0,
            )
            assert result.ok is True


class TestCheckUrl:
    def test_check_url_alive(self):
        from requests_mock import Mocker

        with Mocker() as rm:
            rm.head("https://example.com", status_code=200)
            r = check_url("https://example.com", timeout=5.0)
            assert r.alive is True
            assert r.status_code == 200
            assert r.response_time_ms >= 0

    def test_check_url_5xx_not_alive(self):
        # 5xx means server error → not alive
        from requests_mock import Mocker

        with Mocker() as rm:
            rm.head("https://example.com/error", status_code=503)
            r = check_url("https://example.com/error", timeout=5.0)
            assert r.alive is False
            assert r.status_code == 503

    def test_check_url_dead(self):
        from requests_mock import Mocker

        with Mocker() as rm:
            rm.head("https://dead.example.com", exc=Exception("connection refused"))
            r = check_url("https://dead.example.com", timeout=5.0)
            assert r.alive is False
            assert r.error is not None

    def test_check_url_no_requests(self, monkeypatch):
        import slim_agent.url_fetcher.health as mod

        monkeypatch.setitem(mod.__dict__, "requests", None)
        r = check_url("https://example.com")
        assert r.alive is False
        assert r.error == "requests library not installed"


class TestBatchCheck:
    def test_batch_check_all_alive(self):
        from requests_mock import Mocker

        with Mocker() as rm:
            rm.head("https://a.com", status_code=200)
            rm.head("https://b.com", status_code=200)
            report = batch_check(["https://a.com", "https://b.com"], timeout=5.0)
            assert report.total == 2
            assert report.alive_count == 2
            assert report.dead_count == 0

    def test_batch_check_mixed(self):
        from requests_mock import Mocker

        with Mocker() as rm:
            rm.head("https://alive.com", status_code=200)
            rm.head("https://dead.com", exc=Exception("fail"))
            report = batch_check(["https://alive.com", "https://dead.com"], timeout=5.0)
            assert report.total == 2
            assert report.alive_count == 1
            assert report.dead_count == 1

    def test_batch_check_empty(self):
        report = batch_check([], timeout=5.0)
        assert report.total == 0
        assert report.alive_count == 0


class TestHealthReport:
    def test_alive_count(self):
        from requests_mock import Mocker

        with Mocker() as rm:
            rm.head("https://a.com", status_code=200)
            rm.head("https://b.com", status_code=503)
            rm.head("https://c.com", exc=Exception("fail"))
            report = batch_check(["https://a.com", "https://b.com", "https://c.com"], timeout=5.0)
            assert report.alive_count == 1
            assert report.dead_count == 2

    def test_total_property(self):
        from requests_mock import Mocker

        with Mocker() as rm:
            rm.head("https://x.com", status_code=200)
            report = batch_check(["https://x.com"], timeout=5.0)
            assert report.total == 1