"""Data models for skill manager."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class SkillStatus(str, Enum):
    """Skill lifecycle status."""

    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"

    def can_transition_to(self, target: SkillStatus) -> bool:
        """Return True if a transition from self to target is valid."""
        valid: dict[SkillStatus, set[SkillStatus]] = {
            SkillStatus.DRAFT: {SkillStatus.ACTIVE},
            SkillStatus.ACTIVE: {SkillStatus.DEPRECATED},
            SkillStatus.DEPRECATED: {SkillStatus.ARCHIVED},
            SkillStatus.ARCHIVED: set(),
        }
        return target in valid.get(self, set())


@dataclass
class SkillEntry:
    """A skill entry with lifecycle metadata."""

    id: int | None
    name: str
    summary: str
    tags: list[str]
    status: SkillStatus
    version: str
    code_path: str
    parent_skill_id: int | None
    created_at: datetime
    updated_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "summary": self.summary,
            "tags": self.tags,
            "status": self.status.value,
            "version": self.version,
            "code_path": self.code_path,
            "parent_skill_id": self.parent_skill_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_row(cls, row: tuple[Any, ...], columns: list[str]) -> SkillEntry:
        d = dict(zip(columns, row))
        return cls(
            id=d["id"],
            name=d["name"],
            summary=d["summary"],
            tags=json.loads(d["tags"]) if isinstance(d["tags"], str) else d["tags"],
            status=SkillStatus(d["status"]),
            version=d["version"],
            code_path=d["code_path"],
            parent_skill_id=d["parent_skill_id"],
            created_at=datetime.fromisoformat(d["created_at"]),
            updated_at=datetime.fromisoformat(d["updated_at"]),
        )