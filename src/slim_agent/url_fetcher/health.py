"""URL health-check / liveness probe."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable

try:
    import requests
except ImportError:
    requests = None  # type: ignore


@dataclass
class HealthResult:
    """Health result for a single URL."""

    url: str
    alive: bool
    status_code: int
    response_time_ms: float
    error: str | None = None


@dataclass
class HealthReport:
    """Batch health-check report."""

    results: list[HealthResult] = field(default_factory=list)
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def alive_count(self) -> int:
        return sum(1 for r in self.results if r.alive)

    @property
    def dead_count(self) -> int:
        return self.total - self.alive_count


def check_url(url: str, timeout: float = 5.0) -> HealthResult:
    """Check a single URL's liveness.

    Returns
    -------
    HealthResult
    """
    if requests is None:
        return HealthResult(
            url=url,
            alive=False,
            status_code=0,
            response_time_ms=0.0,
            error="requests library not installed",
        )

    start = time.perf_counter()
    try:
        resp = requests.head(url, timeout=timeout, allow_redirects=True)
        elapsed = (time.perf_counter() - start) * 1000
        alive = 200 <= resp.status_code < 400
        return HealthResult(url=url, alive=alive, status_code=resp.status_code, response_time_ms=elapsed)
    except Exception as exc:
        elapsed = (time.perf_counter() - start) * 1000
        return HealthResult(
            url=url,
            alive=False,
            status_code=0,
            response_time_ms=elapsed,
            error=str(exc),
        )


def batch_check(urls: Iterable[str], timeout: float = 5.0, max_workers: int = 10) -> HealthReport:
    """Check multiple URLs concurrently.

    Parameters
    ----------
    urls : Iterable[str]
    timeout : float
    max_workers : int

    Returns
    -------
    HealthReport
    """
    results: list[HealthResult] = []
    with ThreadPoolExecutor(max_workers=max_workers) as exc:
        futures = {exc.submit(check_url, u, timeout): u for u in urls}
        for fut in as_completed(futures):
            results.append(fut.result())

    return HealthReport(results=results)