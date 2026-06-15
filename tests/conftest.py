"""Shared pytest fixtures and session-level setup."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest


def pytest_configure(config):
    """Activate requests-mock for the whole session before any test module is imported."""
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