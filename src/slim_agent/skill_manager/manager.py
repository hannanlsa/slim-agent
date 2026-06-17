"""Skill lifecycle CRUD and state transitions."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator

from slim_agent.skill_manager.models import SkillEntry, SkillStatus


class SkillManager:
    """CRUD + lifecycle transitions for skills, backed by SQLite."""

    def __init__(self, db_path: str | Path = "slim_agent.db") -> None:
        self.db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
        return self._conn

    @contextmanager
    def _tx(self) -> Generator[sqlite3.Connection, None, None]:
        conn = self._get_conn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def init_db(self) -> None:
        """Create the skills table if it doesn't exist."""
        with self._tx() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS skills (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    summary TEXT NOT NULL DEFAULT '',
                    tags TEXT NOT NULL DEFAULT '[]',
                    status TEXT NOT NULL DEFAULT 'draft',
                    version TEXT NOT NULL DEFAULT '0.1.0',
                    code_path TEXT NOT NULL DEFAULT '',
                    parent_skill_id INTEGER,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (parent_skill_id) REFERENCES skills(id)
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_skills_status ON skills(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_skills_name ON skills(name)")

    # ── helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _cols(cur: sqlite3.Cursor) -> list[str]:
        return [d[0] for d in cur.description or []]

    @staticmethod
    def _from_row(row: tuple[Any, ...], cols: list[str]) -> SkillEntry:
        return SkillEntry.from_row(row, cols)

    @staticmethod
    def _fetch_one(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...]) -> tuple[Any, ...] | None:
        cur = conn.execute(sql, params)
        r = cur.fetchone()
        return tuple(r) if r else None

    # ── CRUD ─────────────────────────────────────────────────────────────────

    def add_skill(
        self,
        name: str,
        summary: str = "",
        tags: list[str] | None = None,
        code_path: str = "",
    ) -> SkillEntry:
        """Create a new skill in DRAFT status."""
        tags = tags or []
        now = datetime.now(timezone.utc).isoformat()
        with self._tx() as conn:
            cur = conn.execute(
                """
                INSERT INTO skills (name, summary, tags, code_path, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (name, summary, json.dumps(tags), code_path, now, now),
            )
            rowid = cur.lastrowid
            assert rowid is not None
            row = self._fetch_one(conn, "SELECT * FROM skills WHERE id = ?", (rowid,))
            cols = self._cols(conn.execute("SELECT * FROM skills WHERE id = ?", (rowid,)))
        return self._from_row(row, cols) if row else self._from_row((), cols)

    def get_skill(self, sid: int) -> SkillEntry | None:
        row = self._fetch_one(self._get_conn(), "SELECT * FROM skills WHERE id = ?", (sid,))
        if row is None:
            return None
        cols = self._cols(self._get_conn().execute("SELECT * FROM skills WHERE id = ?", (sid,)))
        return self._from_row(row, cols)

    def list_by_status(self, status: SkillStatus) -> list[SkillEntry]:
        conn = self._get_conn()
        cur = conn.execute(
            "SELECT * FROM skills WHERE status = ? ORDER BY created_at DESC",
            (status.value,),
        )
        cols = self._cols(cur)
        return [self._from_row(tuple(r), cols) for r in cur.fetchall()]

    def list_all(self) -> list[SkillEntry]:
        conn = self._get_conn()
        cur = conn.execute("SELECT * FROM skills ORDER BY created_at DESC")
        cols = self._cols(cur)
        return [self._from_row(tuple(r), cols) for r in cur.fetchall()]

    def search(self, keyword: str) -> list[SkillEntry]:
        """Simple LIKE search on name and summary."""
        conn = self._get_conn()
        pattern = f"%{keyword}%"
        cur = conn.execute(
            "SELECT * FROM skills WHERE name LIKE ? OR summary LIKE ? ORDER BY created_at DESC",
            (pattern, pattern),
        )
        cols = self._cols(cur)
        return [self._from_row(tuple(r), cols) for r in cur.fetchall()]

    def delete_skill(self, sid: int) -> bool:
        conn = self._get_conn()
        cur = conn.execute("DELETE FROM skills WHERE id = ?", (sid,))
        conn.commit()
        return cur.rowcount > 0

    # ── Lifecycle transitions ───────────────────────────────────────────────

    def _transition(self, sid: int, target: SkillStatus) -> SkillEntry:
        """Apply a lifecycle transition. Caller is responsible for validity check."""
        now = datetime.now(timezone.utc).isoformat()
        with self._tx() as conn:
            conn.execute(
                "UPDATE skills SET status = ?, updated_at = ? WHERE id = ?",
                (target.value, now, sid),
            )
            row = self._fetch_one(conn, "SELECT * FROM skills WHERE id = ?", (sid,))
            cols = self._cols(conn.execute("SELECT * FROM skills WHERE id = ?", (sid,)))
        if row is None:
            raise ValueError(f"Skill {sid} not found")
        return self._from_row(row, cols)

    def activate(self, sid: int) -> SkillEntry:
        """Transition DRAFT → ACTIVE."""
        skill = self.get_skill(sid)
        if skill is None:
            raise ValueError(f"Skill {sid} not found")
        if not skill.status.can_transition_to(SkillStatus.ACTIVE):
            raise ValueError(
                f"Cannot transition {skill.status.value} → active "
                f"(skill {sid}): invalid state path"
            )
        return self._transition(sid, SkillStatus.ACTIVE)

    def deprecate(self, sid: int) -> SkillEntry:
        """Transition ACTIVE → DEPRECATED."""
        skill = self.get_skill(sid)
        if skill is None:
            raise ValueError(f"Skill {sid} not found")
        if not skill.status.can_transition_to(SkillStatus.DEPRECATED):
            raise ValueError(
                f"Cannot transition {skill.status.value} → deprecated "
                f"(skill {sid}): invalid state path"
            )
        return self._transition(sid, SkillStatus.DEPRECATED)

    def archive(self, sid: int) -> SkillEntry:
        """Transition DEPRECATED → ARCHIVED."""
        skill = self.get_skill(sid)
        if skill is None:
            raise ValueError(f"Skill {sid} not found")
        if not skill.status.can_transition_to(SkillStatus.ARCHIVED):
            raise ValueError(
                f"Cannot transition {skill.status.value} → archived "
                f"(skill {sid}): invalid state path"
            )
        return self._transition(sid, SkillStatus.ARCHIVED)

    def upgrade(self, sid: int, reason: str = "") -> SkillEntry:
        """Bump version patch-level, link to parent, and optionally record reason."""
        skill = self.get_skill(sid)
        if skill is None:
            raise ValueError(f"Skill {sid} not found")

        parts = skill.version.rsplit(".", 1)
        try:
            new_ver = f"{parts[0]}.{int(parts[1]) + 1}"
        except Exception:
            new_ver = skill.version + ".1"

        now = datetime.now(timezone.utc).isoformat()
        parent_ref = skill.parent_skill_id if skill.parent_skill_id is not None else sid
        with self._tx() as conn:
            conn.execute(
                "UPDATE skills SET version = ?, parent_skill_id = ?, updated_at = ? WHERE id = ?",
                (new_ver, parent_ref, now, sid),
            )
            row = self._fetch_one(conn, "SELECT * FROM skills WHERE id = ?", (sid,))
            cols = self._cols(conn.execute("SELECT * FROM skills WHERE id = ?", (sid,)))
        if row is None:
            raise ValueError(f"Skill {sid} not found after upgrade")

        # Record upgrade reason to ReflectionPool if provided
        if reason:
            try:
                from ..reflection_pool import ReflectionPool
                pool = ReflectionPool()
                pool.add(
                    title=f"skill-upgrade: {skill.name} → v{new_ver}",
                    content=reason,
                    tags=["skill-upgrade", skill.name],
                    source="evolution",
                    reason=reason,
                )
                pool.close()
            except Exception:
                pass  # ponytail: L5 — ReflectionPool 写入失败不影响 upgrade 主流程

        return self._from_row(row, cols)

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None