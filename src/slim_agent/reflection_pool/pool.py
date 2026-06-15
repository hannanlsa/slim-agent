"""Append-only reflection pool for lessons learned from errors."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator

from slim_agent.reflection_pool.models import ReflectionEntry


class ReflectionPool:
    """Append-only store for reflection entries."""

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
        """Create the reflections table if it doesn't exist."""
        with self._tx() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS reflections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    error_type TEXT NOT NULL,
                    error_message TEXT NOT NULL,
                    context TEXT NOT NULL DEFAULT '',
                    lesson_learned TEXT NOT NULL DEFAULT '',
                    related_skill_id INTEGER,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_reflections_error_type ON reflections(error_type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_reflections_related ON reflections(related_skill_id)")

    # ── helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _cols(cur: sqlite3.Cursor) -> list[str]:
        return [d[0] for d in cur.description or []]

    @staticmethod
    def _from_row(row: tuple[Any, ...], cols: list[str]) -> ReflectionEntry:
        return ReflectionEntry.from_row(row, cols)

    @staticmethod
    def _fetch_one(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...]) -> tuple[Any, ...] | None:
        cur = conn.execute(sql, params)
        r = cur.fetchone()
        return tuple(r) if r else None

    # ── Append-only writes ───────────────────────────────────────────────────

    def add(
        self,
        error_type: str,
        error_message: str,
        context: str = "",
        lesson_learned: str = "",
        related_skill_id: int | None = None,
    ) -> ReflectionEntry:
        """Append a new reflection entry (append-only — no update, no delete)."""
        now = datetime.now(timezone.utc).isoformat()
        with self._tx() as conn:
            cur = conn.execute(
                """
                INSERT INTO reflections (error_type, error_message, context, lesson_learned, related_skill_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (error_type, error_message, context, lesson_learned, related_skill_id, now),
            )
            rowid = cur.lastrowid
            assert rowid is not None
            row = self._fetch_one(conn, "SELECT * FROM reflections WHERE id = ?", (rowid,))
            cols = self._cols(conn.execute("SELECT * FROM reflections WHERE id = ?", (rowid,)))
        return self._from_row(row, cols) if row else self._from_row((), cols)

    # ── Reads ────────────────────────────────────────────────────────────────

    def list_all(self) -> list[ReflectionEntry]:
        conn = self._get_conn()
        cur = conn.execute("SELECT * FROM reflections ORDER BY created_at DESC")
        cols = self._cols(cur)
        return [self._from_row(tuple(r), cols) for r in cur.fetchall()]

    def query_by_error_type(self, error_type: str) -> list[ReflectionEntry]:
        conn = self._get_conn()
        cur = conn.execute(
            "SELECT * FROM reflections WHERE error_type = ? ORDER BY created_at DESC",
            (error_type,),
        )
        cols = self._cols(cur)
        return [self._from_row(tuple(r), cols) for r in cur.fetchall()]

    def query_by_skill(self, skill_id: int) -> list[ReflectionEntry]:
        conn = self._get_conn()
        cur = conn.execute(
            "SELECT * FROM reflections WHERE related_skill_id = ? ORDER BY created_at DESC",
            (skill_id,),
        )
        cols = self._cols(cur)
        return [self._from_row(tuple(r), cols) for r in cur.fetchall()]

    def search_lessons(self, keyword: str) -> list[ReflectionEntry]:
        """Search across lesson_learned and context."""
        conn = self._get_conn()
        pattern = f"%{keyword}%"
        cur = conn.execute(
            """
            SELECT * FROM reflections
            WHERE lesson_learned LIKE ? OR context LIKE ?
            ORDER BY created_at DESC
            """,
            (pattern, pattern),
        )
        cols = self._cols(cur)
        return [self._from_row(tuple(r), cols) for r in cur.fetchall()]

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None