"""URL fetching with HTML→text extraction and fallback support."""

# ponytail: L2 stdlib-ok | 已知限制：urllib 无 HTTP/2、无连接池复用 | 升级：如需高性能可换 httpx

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError


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
    try:
        req = Request(url, headers={"User-Agent": "SLIM-Agent/0.2"})
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            content = _html_to_text(raw)
            return FetchResult(
                url=url,
                content=content,
                status_code=resp.status,
                fetched_at=datetime.now(timezone.utc),
            )
    except HTTPError as exc:
        return FetchResult(
            url=url,
            content="",
            status_code=exc.code,
            fetched_at=datetime.now(timezone.utc),
            error=str(exc),
        )
    except (URLError, OSError) as exc:
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


if __name__ == "__main__":
    # ponytail: L2 self-test — urllib 替代 requests 的基本验证
    r = fetch_content("https://httpbin.org/get")
    assert r.ok, f"fetch failed: {r.error}"
    assert "SLIM-Agent" in r.content or "url" in r.content.lower(), f"unexpected content: {r.content[:200]}"
    print(f"✓ fetch_content ok (status={r.status_code}, content_len={len(r.content)})")
