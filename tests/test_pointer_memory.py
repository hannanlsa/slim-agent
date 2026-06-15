"""Tests for pointer_memory module."""

import json
import tempfile
import time
from pathlib import Path

import pytest

from slim_agent.pointer_memory import PointerEntry, PointerStore


@pytest.fixture
def db_path():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        p = Path(f.name)
    yield p
    p.unlink(missing_ok=True)


@pytest.fixture
def store(db_path):
    s = PointerStore(db_path)
    s.init_db()
    yield s
    s.close()


class TestPointerStore:
    def test_add_pointer(self, store):
        entry = store.add_pointer(
            summary="SQLite FTS5 guide",
            primary_url="https://sqlite.org/fts5.html",
            tags=["sqlite", "search"],
            fallback_urls=["https://mirror.example.com/fts5.html"],
        )
        assert entry.id is not None
        assert entry.summary == "SQLite FTS5 guide"
        assert entry.primary_url == "https://sqlite.org/fts5.html"
        assert entry.tags == ["sqlite", "search"]
        assert entry.fallback_urls == ["https://mirror.example.com/fts5.html"]
        assert entry.access_count == 0

    def test_add_pointer_minimal(self, store):
        entry = store.add_pointer(summary="minimal", primary_url="https://x.com")
        assert entry.id is not None
        assert entry.tags == []
        assert entry.fallback_urls == []

    def test_get_pointer(self, store):
        added = store.add_pointer(summary="test get", primary_url="https://x.com")
        fetched = store.get_pointer(added.id)
        assert fetched is not None
        assert fetched.id == added.id
        assert fetched.summary == "test get"
        assert fetched.access_count == 1

    def test_get_pointer_increments_count(self, store):
        added = store.add_pointer(summary="count test", primary_url="https://x.com")
        store.get_pointer(added.id)
        store.get_pointer(added.id)
        fetched = store.get_pointer(added.id)
        assert fetched.access_count == 3

    def test_get_pointer_not_found(self, store):
        result = store.get_pointer(9999)
        assert result is None

    def test_list_all_empty(self, store):
        assert store.list_all() == []

    def test_list_all(self, store):
        store.add_pointer(summary="a", primary_url="https://a.com")
        store.add_pointer(summary="b", primary_url="https://b.com")
        entries = store.list_all()
        assert len(entries) == 2

    def test_search_by_keyword(self, store):
        store.add_pointer(summary="Python SQLite tutorial", primary_url="https://a.com")
        store.add_pointer(summary="JavaScript guide", primary_url="https://b.com")
        results = store.search_by_keyword("sqlite")
        assert len(results) >= 1
        assert any("sqlite" in r.summary.lower() for r in results)

    def test_search_by_keyword_no_results(self, store):
        store.add_pointer(summary="Python guide", primary_url="https://a.com")
        results = store.search_by_keyword("nonexistentkeyword12345")
        assert results == []

    def test_search_by_tag(self, store):
        store.add_pointer(summary="a", primary_url="https://a.com", tags=["python"])
        store.add_pointer(summary="b", primary_url="https://b.com", tags=["javascript"])
        results = store.search_by_tag("python")
        assert len(results) == 1
        assert results[0].summary == "a"

    def test_search_by_tag_no_results(self, store):
        store.add_pointer(summary="a", primary_url="https://a.com", tags=["python"])
        results = store.search_by_tag("nonexistent")
        assert results == []

    def test_delete_pointer(self, store):
        added = store.add_pointer(summary="delete me", primary_url="https://x.com")
        ok = store.delete_pointer(added.id)
        assert ok is True
        assert store.get_pointer(added.id) is None

    def test_delete_pointer_not_found(self, store):
        ok = store.delete_pointer(9999)
        assert ok is False

    def test_to_dict(self, store):
        entry = store.add_pointer(summary="dict test", primary_url="https://x.com", tags=["test"])
        d = entry.to_dict()
        assert d["summary"] == "dict test"
        assert d["primary_url"] == "https://x.com"
        assert d["tags"] == ["test"]
        assert isinstance(d["created_at"], str)
        assert isinstance(d["updated_at"], str)


class TestPointerEntryFromRow:
    def test_from_row(self, store):
        entry = store.add_pointer(summary="row test", primary_url="https://x.com", tags=["tag1"])
        cur = store._get_conn().execute("SELECT * FROM pointers WHERE id = ?", (entry.id,))
        cols = [d[0] for d in (cur.description or [])]
        row = cur.fetchone()
        rebuilt = PointerEntry.from_row(tuple(row), cols)
        assert rebuilt.id == entry.id
        assert rebuilt.summary == entry.summary
        assert rebuilt.tags == ["tag1"]