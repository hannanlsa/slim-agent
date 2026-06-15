"""Data models for reflection pool."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class ReflectionEntry:
    """A lesson learned from a failure or error."""

    id: int | None
    error_type: str
    error_message: str
    context: str
    lesson_learned: str
    related_skill_id: int | None
    created_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "context": self.context,
            "lesson_learned": self.lesson_learned,
            "related_skill_id": self.related_skill_id,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_row(cls, row: tuple[Any, ...], columns: list[str]) -> ReflectionEntry:
        d = dict(zip(columns, row))
        return cls(
            id=d["id"],
            error_type=d["error_type"],
            error_message=d["error_message"],
            context=d["context"],
            lesson_learned=d["lesson_learned"],
            related_skill_id=d["related_skill_id"],
            created_at=datetime.fromisoformat(d["created_at"]),
        )