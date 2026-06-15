"""SQLite-backed pointer memory store."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator

from slim_agent.pointer_memory.models import PointerEntry


class PointerStore:
    """CRUD store for pointer entries backed by SQLite."""

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
        """Create tables and FTS5 virtual table if they don't exist."""
        with self._tx() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS pointers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    summary TEXT NOT NULL,
                    tags TEXT NOT NULL DEFAULT '[]',
                    primary_url TEXT NOT NULL,
                    fallback_urls TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    access_count INTEGER NOT NULL DEFAULT 0,
                    last_accessed TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_pointers_created ON pointers(created_at);

                CREATE VIRTUAL TABLE IF NOT EXISTS pointers_fts USING fts5(
                    summary,
                    content='pointers',
                    content_rowid='id',
                    tokenize='trigram'
                );

                CREATE TRIGGER IF NOT EXISTS pointers_fts_insert AFTER INSERT ON pointers BEGIN
                    INSERT INTO pointers_fts(rowid, summary) VALUES (new.id, new.summary);
                END;

                CREATE TRIGGER IF NOT EXISTS pointers_fts_update AFTER UPDATE ON pointers BEGIN
                    INSERT INTO pointers_fts(pointers_fts, rowid, summary) VALUES('delete', old.id, old.summary);
                    INSERT INTO pointers_fts(rowid, summary) VALUES (new.id, new.summary);
                END;

                CREATE TRIGGER IF NOT EXISTS pointers_fts_delete AFTER DELETE ON pointers BEGIN
                    INSERT INTO pointers_fts(pointers_fts, rowid, summary) VALUES('delete', old.id, old.summary);
                END;
                """
            )

    # ── helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _cols(cur: sqlite3.Cursor) -> list[str]:
        """Extract column names from a cursor description."""
        return [d[0] for d in cur.description or []]

    @staticmethod
    def _from_row(row: tuple[Any, ...], cols: list[str]) -> PointerEntry:
        return PointerEntry.from_row(row, cols)

    # ── CRUD ────────────────────────────────────────────────────────────────────

    def add_pointer(
        self,
        summary: str,
        primary_url: str,
        tags: list[str] | None = None,
        fallback_urls: list[str] | None = None,
    ) -> PointerEntry:
        """Insert a new pointer entry."""
        tags = tags or []
        fallback_urls = fallback_urls or []
        now = datetime.now(timezone.utc).isoformat()
        with self._tx() as conn:
            cur = conn.execute(
                """
                INSERT INTO pointers (summary, tags, primary_url, fallback_urls, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (summary, json.dumps(tags), primary_url, json.dumps(fallback_urls), now, now),
            )
            rowid = cur.lastrowid
            assert rowid is not None
            cur2 = conn.execute("SELECT * FROM pointers WHERE id = ?", (rowid,))
            r = cur2.fetchone()
            cols = self._cols(cur2)
        return self._from_row(tuple(r), cols) if r else self._from_row((), cols)

    def get_pointer(self, pid: int) -> PointerEntry | None:
        """Fetch by id, incrementing access_count."""
        conn = self._get_conn()
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE pointers SET access_count = access_count + 1, last_accessed = ? WHERE id = ?",
            (now, pid),
        )
        conn.commit()
        cur = conn.execute("SELECT * FROM pointers WHERE id = ?", (pid,))
        r = cur.fetchone()
        if r is None:
            return None
        cols = self._cols(cur)
        return self._from_row(tuple(r), cols)

    def list_all(self) -> list[PointerEntry]:
        """Return all pointer entries ordered by created_at desc."""
        conn = self._get_conn()
        cur = conn.execute("SELECT * FROM pointers ORDER BY created_at DESC")
        cols = self._cols(cur)
        return [self._from_row(tuple(r), cols) for r in cur.fetchall()]

    def search_by_keyword(self, keyword: str) -> list[PointerEntry]:
        """FTS5 full-text search on summary."""
        conn = self._get_conn()
        safe = '"' + keyword.replace('"', "") + '"'
        cur = conn.execute(
            f"""
            SELECT p.* FROM pointers p
            JOIN pointers_fts f ON p.id = f.rowid
            WHERE pointers_fts MATCH ?
            ORDER BY p.access_count DESC, p.created_at DESC
            """,
            (safe,),
        )
        cols = self._cols(cur)
        results = [self._from_row(tuple(r), cols) for r in cur.fetchall()]
        # Bump access count for each hit
        now = datetime.now(timezone.utc).isoformat()
        for entry in results:
            if entry.id is not None:
                conn.execute(
                    "UPDATE pointers SET access_count = access_count + 1, last_accessed = ? WHERE id = ?",
                    (now, entry.id),
                )
        conn.commit()
        return results

    def search_by_tag(self, tag: str) -> list[PointerEntry]:
        """Return entries whose tags JSON array contains the given tag."""
        conn = self._get_conn()
        cur = conn.execute(
            "SELECT * FROM pointers WHERE tags LIKE ? ORDER BY created_at DESC",
            (f'%"{tag}"%',),
        )
        cols = self._cols(cur)
        return [self._from_row(tuple(r), cols) for r in cur.fetchall()]

    def delete_pointer(self, pid: int) -> bool:
        """Delete by id. Returns True if a row was deleted."""
        conn = self._get_conn()
        cur = conn.execute("DELETE FROM pointers WHERE id = ?", (pid,))
        conn.commit()
        return cur.rowcount > 0

    def close(self) -> None:
        """Close the underlying connection."""
        if self._conn:
            self._conn.close()
            self._conn = None