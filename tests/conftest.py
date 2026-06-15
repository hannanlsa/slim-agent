"""Shared pytest fixtures and session-level setup."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest


def pytest_configure(config):
    """Activate requests-mock for the whole session before any test module is imported.

    Tests that need real HTTP (test_real_world.py) can call the
    `real_http` fixture to temporarily stop the session mock for that test.
    """
    try:
        from requests_mock import Mocker
    except ImportError:
        return  # requests-mock not installed; HTTP tests will be skipped
    global _session_mocker
    _session_mocker = Mocker()
    _session_mocker.start()


_session_mocker = None


def pytest_unconfigure(config):
    if _session_mocker is not None:
        _session_mocker.stop()


@pytest.fixture
def real_http():
    """Temporarily disable the session-level requests-mock for a single test.

    Use this in tests that hit real HTTP endpoints (e.g. httpbin.org).
    The mock is restarted after the test, so other tests keep their mock.

    Example:
        def test_fetch_live(real_http):
            result = fetch_with_fallback("https://httpbin.org/html", ...)
            assert result.ok
    """
    if _session_mocker is not None:
        _session_mocker.stop()
    yield
    if _session_mocker is not None:
        # Restart the session mocker; tests after this one will still be mocked
        _session_mocker.start()
