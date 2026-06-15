"""URL fetcher module."""

from slim_agent.url_fetcher.fetcher import FetchResult, fetch_content, fetch_with_fallback
from slim_agent.url_fetcher.health import HealthReport, HealthResult, batch_check, check_url

__all__ = [
    "FetchResult",
    "fetch_content",
    "fetch_with_fallback",
    "HealthReport",
    "HealthResult",
    "batch_check",
    "check_url",
]