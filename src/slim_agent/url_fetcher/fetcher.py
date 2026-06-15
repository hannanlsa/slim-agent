"""URL fetching with HTML→text extraction and fallback support."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

try:
    import requests
except ImportError:
    requests = None  # type: ignore


_STripper = re.compile(r"<[^>]+>")


def _html_to_text(html: str) -> str:
    """Strip HTML tags, decode entities, collapse whitespace."""
    text = _STripper.sub(" ", html)
    text = re.sub(r"&[a-zA-Z]+;", _entity_replace, text)
    text = re.sub(r"&#\d+;", _num_entity_replace, text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _entity_replace(m: re.Match[str]) -> str:
    entities = {
        "&amp;": "&",
        "&lt;": "<",
        "&gt;": ">",
        "&quot;": '"',
        "&apos;": "'",
        "&nbsp;": " ",
        "&mdash;": "—",
        "&ndash;": "–",
        "&hellip;": "…",
    }
    return entities.get(m.group(0), m.group(0))


def _num_entity_replace(m: re.Match[str]) -> str:
    try:
        return chr(int(m.group(0)[2:], 10))
    except Exception:
        return m.group(0)


@dataclass
class FetchResult:
    """Result of a URL fetch operation."""

    url: str
    content: str
    status_code: int
    fetched_at: datetime
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and 200 <= self.status_code < 400


def fetch_content(url: str, timeout: float = 10.0) -> FetchResult:
    """Fetch a URL and extract readable text from its HTML body.

    Parameters
    ----------
    url : str
        The URL to fetch.
    timeout : float
        Request timeout in seconds (default 10).

    Returns
    -------
    FetchResult
        Always returned; check ``result.ok`` for success.
    """
    if requests is None:
        return FetchResult(
            url=url,
            content="",
            status_code=0,
            fetched_at=datetime.now(timezone.utc),
            error="requests library not installed",
        )

    try:
        resp = requests.get(url, timeout=timeout, headers={"User-Agent": "SLIM-Agent/0.1"}, stream=True)
        raw = resp.content.decode("utf-8", errors="replace")
        content = _html_to_text(raw)
        return FetchResult(
            url=url,
            content=content,
            status_code=resp.status_code,
            fetched_at=datetime.now(timezone.utc),
        )
    except Exception as exc:
        return FetchResult(
            url=url,
            content="",
            status_code=0,
            fetched_at=datetime.now(timezone.utc),
            error=str(exc),
        )


def fetch_with_fallback(
    primary_url: str,
    fallback_urls: list[str],
    timeout: float = 10.0,
) -> FetchResult:
    """Try primary_url first, then each fallback in order until success.

    Parameters
    ----------
    primary_url : str
    fallback_urls : list[str]
    timeout : float

    Returns
    -------
    FetchResult
        First successful result, or last failure result.
    """
    all_urls = [primary_url] + list(fallback_urls)
    last: FetchResult | None = None
    for u in all_urls:
        result = fetch_content(u, timeout=timeout)
        if result.ok:
            return result
        last = result
    return last or FetchResult(
        url=primary_url,
        content="",
        status_code=0,
        fetched_at=datetime.now(timezone.utc),
        error="No URLs provided",
    )