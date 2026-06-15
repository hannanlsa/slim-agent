"""Data models for pointer memory."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class PointerEntry:
    """A pointer-style knowledge entry (summary + URL, no full text)."""

    id: int | None
    summary: str
    tags: list[str]
    primary_url: str
    fallback_urls: list[str]
    created_at: datetime
    updated_at: datetime
    access_count: int = 0
    last_accessed: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {
            "id": self.id,
            "summary": self.summary,
            "tags": self.tags,
            "primary_url": self.primary_url,
            "fallback_urls": self.fallback_urls,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "access_count": self.access_count,
            "last_accessed": self.last_accessed.isoformat() if self.last_accessed else None,
        }

    @classmethod
    def from_row(cls, row: tuple[Any, ...], columns: list[str]) -> PointerEntry:
        """Build from a DB row and its column names."""
        d = dict(zip(columns, row))
        return cls(
            id=d["id"],
            summary=d["summary"],
            tags=json.loads(d["tags"]) if isinstance(d["tags"], str) else d["tags"],
            primary_url=d["primary_url"],
            fallback_urls=json.loads(d["fallback_urls"]) if isinstance(d["fallback_urls"], str) else d["fallback_urls"],
            created_at=datetime.fromisoformat(d["created_at"]),
            updated_at=datetime.fromisoformat(d["updated_at"]),
            access_count=d["access_count"],
            last_accessed=datetime.fromisoformat(d["last_accessed"]) if d["last_accessed"] else None,
        )