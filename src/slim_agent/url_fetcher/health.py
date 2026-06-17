"""URL health-check / liveness probe."""

# ponytail: L2 stdlib-ok | 已知限制：urllib 无 HEAD 自动重试 | 升级：如需重试可加 urllib.retry（Python 3.11+）

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError


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
    start = time.perf_counter()
    try:
        req = Request(url, method="HEAD", headers={"User-Agent": "SLIM-Agent/0.2"})
        with urlopen(req, timeout=timeout) as resp:
            elapsed = (time.perf_counter() - start) * 1000
            alive = 200 <= resp.status < 400
            return HealthResult(url=url, alive=alive, status_code=resp.status, response_time_ms=elapsed)
    except HTTPError as exc:
        elapsed = (time.perf_counter() - start) * 1000
        alive = 200 <= exc.code < 400
        return HealthResult(url=url, alive=alive, status_code=exc.code, response_time_ms=elapsed, error=str(exc))
    except (URLError, OSError) as exc:
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


if __name__ == "__main__":
    # ponytail: L2 self-test — urllib HEAD 健康检查基本验证
    r = check_url("https://httpbin.org/get", timeout=10)
    assert r.alive, f"health check failed: {r.error}"
    print(f"✓ check_url ok (status={r.status_code}, {r.response_time_ms:.0f}ms)")
