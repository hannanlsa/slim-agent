"""Tests for reflection_pool module."""

import tempfile
from pathlib import Path

import pytest

from slim_agent.reflection_pool import ReflectionEntry, ReflectionPool


@pytest.fixture
def db_path():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        p = Path(f.name)
    yield p
    p.unlink(missing_ok=True)


@pytest.fixture
def pool(db_path):
    p = ReflectionPool(db_path)
    p.init_db()
    yield p
    p.close()


class TestReflectionPool:
    def test_add(self, pool):
        entry = pool.add(
            error_type="TimeoutError",
            error_message="request timed out",
            context="fetching https://example.com",
            lesson_learned="always set a timeout",
            related_skill_id=1,
        )
        assert entry.id is not None
        assert entry.error_type == "TimeoutError"
        assert entry.error_message == "request timed out"
        assert entry.lesson_learned == "always set a timeout"
        assert entry.related_skill_id == 1

    def test_add_minimal(self, pool):
        entry = pool.add(error_type="RuntimeError", error_message="crash")
        assert entry.id is not None
        assert entry.context == ""
        assert entry.lesson_learned == ""
        assert entry.related_skill_id is None

    def test_list_all(self, pool):
        pool.add(error_type="A", error_message="a")
        pool.add(error_type="B", error_message="b")
        entries = pool.list_all()
        assert len(entries) == 2

    def test_query_by_error_type(self, pool):
        pool.add(error_type="TimeoutError", error_message="t1")
        pool.add(error_type="TimeoutError", error_message="t2")
        pool.add(error_type="RuntimeError", error_message="r1")
        results = pool.query_by_error_type("TimeoutError")
        assert len(results) == 2
        assert all(e.error_type == "TimeoutError" for e in results)

    def test_query_by_skill(self, pool):
        pool.add(error_type="A", error_message="a", related_skill_id=1)
        pool.add(error_type="B", error_message="b", related_skill_id=2)
        pool.add(error_type="C", error_message="c", related_skill_id=1)
        results = pool.query_by_skill(1)
        assert len(results) == 2
        assert all(e.related_skill_id == 1 for e in results)

    def test_search_lessons(self, pool):
        pool.add(
            error_type="TimeoutError",
            error_message="timeout",
            lesson_learned="set a timeout on all HTTP requests",
        )
        pool.add(
            error_type="ValueError",
            error_message="bad input",
            lesson_learned="validate input before processing",
        )
        results = pool.search_lessons("timeout")
        assert len(results) >= 1
        assert any("timeout" in r.lesson_learned.lower() for r in results)

    def test_search_lessons_context(self, pool):
        pool.add(
            error_type="Error",
            error_message="msg",
            context="the context mentions memory leak",
            lesson_learned="fix it",
        )
        results = pool.search_lessons("memory leak")
        assert len(results) == 1


class TestReflectionEntry:
    def test_to_dict(self, pool):
        entry = pool.add(error_type="TestError", error_message="test", lesson_learned="be careful")
        d = entry.to_dict()
        assert d["error_type"] == "TestError"
        assert d["error_message"] == "test"
        assert d["lesson_learned"] == "be careful"
        assert isinstance(d["created_at"], str)

    def test_from_row(self, pool):
        entry = pool.add(error_type="FromRowTest", error_message="fr", related_skill_id=42)
        cur = pool._get_conn().execute("SELECT * FROM reflections WHERE id = ?", (entry.id,))
        cols = [d[0] for d in (cur.description or [])]
        row = cur.fetchone()
        rebuilt = ReflectionEntry.from_row(tuple(row), cols)
        assert rebuilt.error_type == "FromRowTest"
        assert rebuilt.related_skill_id == 42