"""Tests for skill_manager module."""

import tempfile
from pathlib import Path

import pytest

from slim_agent.skill_manager import SkillManager, SkillEntry, SkillStatus


@pytest.fixture
def db_path():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        p = Path(f.name)
    yield p
    p.unlink(missing_ok=True)


@pytest.fixture
def mgr(db_path):
    m = SkillManager(db_path)
    m.init_db()
    yield m
    m.close()


class TestSkillStatus:
    def test_can_transition_draft_to_active(self):
        assert SkillStatus.DRAFT.can_transition_to(SkillStatus.ACTIVE) is True

    def test_cannot_transition_draft_to_archived(self):
        assert SkillStatus.DRAFT.can_transition_to(SkillStatus.ARCHIVED) is False

    def test_cannot_transition_draft_to_deprecated(self):
        assert SkillStatus.DRAFT.can_transition_to(SkillStatus.DEPRECATED) is False

    def test_can_transition_active_to_deprecated(self):
        assert SkillStatus.ACTIVE.can_transition_to(SkillStatus.DEPRECATED) is True

    def test_can_transition_deprecated_to_archived(self):
        assert SkillStatus.DEPRECATED.can_transition_to(SkillStatus.ARCHIVED) is True

    def test_cannot_transition_archived(self):
        assert SkillStatus.ARCHIVED.can_transition_to(SkillStatus.ARCHIVED) is False
        assert SkillStatus.ARCHIVED.can_transition_to(SkillStatus.ACTIVE) is False

    def test_status_values(self):
        assert SkillStatus.DRAFT.value == "draft"
        assert SkillStatus.ACTIVE.value == "active"
        assert SkillStatus.DEPRECATED.value == "deprecated"
        assert SkillStatus.ARCHIVED.value == "archived"


class TestSkillManager:
    def test_add_skill(self, mgr):
        skill = mgr.add_skill(name="test-skill", summary="does things", tags=["test", "automation"])
        assert skill.id is not None
        assert skill.name == "test-skill"
        assert skill.summary == "does things"
        assert skill.tags == ["test", "automation"]
        assert skill.status == SkillStatus.DRAFT
        assert skill.version == "0.1.0"
        assert skill.parent_skill_id is None

    def test_add_skill_unique_name(self, mgr):
        mgr.add_skill(name="unique-name")
        with pytest.raises(Exception):  # UNIQUE constraint violation
            mgr.add_skill(name="unique-name")

    def test_get_skill(self, mgr):
        added = mgr.add_skill(name="get-test")
        fetched = mgr.get_skill(added.id)
        assert fetched is not None
        assert fetched.name == "get-test"

    def test_get_skill_not_found(self, mgr):
        assert mgr.get_skill(9999) is None

    def test_list_all(self, mgr):
        mgr.add_skill(name="a")
        mgr.add_skill(name="b")
        entries = mgr.list_all()
        assert len(entries) == 2

    def test_list_by_status(self, mgr):
        mgr.add_skill(name="draft-skill")
        active = mgr.add_skill(name="active-skill")
        mgr.activate(active.id)

        drafts = mgr.list_by_status(SkillStatus.DRAFT)
        actives = mgr.list_by_status(SkillStatus.ACTIVE)

        assert any(s.name == "draft-skill" for s in drafts)
        assert any(s.name == "active-skill" for s in actives)
        assert all(s.status == SkillStatus.DRAFT for s in drafts)
        assert all(s.status == SkillStatus.ACTIVE for s in actives)

    def test_activate(self, mgr):
        skill = mgr.add_skill(name="activate-me")
        activated = mgr.activate(skill.id)
        assert activated.status == SkillStatus.ACTIVE

    def test_activate_invalid_transition(self, mgr):
        skill = mgr.add_skill(name="test")
        mgr.activate(skill.id)
        with pytest.raises(ValueError, match="Cannot transition"):
            mgr.activate(skill.id)  # already active

    def test_activate_not_found(self, mgr):
        with pytest.raises(ValueError, match="not found"):
            mgr.activate(9999)

    def test_deprecate(self, mgr):
        skill = mgr.add_skill(name="test")
        mgr.activate(skill.id)
        deprecated = mgr.deprecate(skill.id)
        assert deprecated.status == SkillStatus.DEPRECATED

    def test_deprecate_invalid_transition(self, mgr):
        skill = mgr.add_skill(name="test")  # draft
        with pytest.raises(ValueError, match="Cannot transition"):
            mgr.deprecate(skill.id)

    def test_archive(self, mgr):
        skill = mgr.add_skill(name="test")
        mgr.activate(skill.id)
        mgr.deprecate(skill.id)
        archived = mgr.archive(skill.id)
        assert archived.status == SkillStatus.ARCHIVED

    def test_archive_invalid_transition(self, mgr):
        skill = mgr.add_skill(name="test")
        mgr.activate(skill.id)
        with pytest.raises(ValueError, match="Cannot transition"):
            mgr.archive(skill.id)  # must be deprecated first

    def test_upgrade(self, mgr):
        skill = mgr.add_skill(name="test")
        assert skill.version == "0.1.0"
        upgraded = mgr.upgrade(skill.id)
        assert upgraded.version == "0.1.1"

    def test_upgrade_semver_three_parts(self, mgr):
        skill = mgr.add_skill(name="test")
        # Update DB directly to a three-part semver version
        mgr._get_conn().execute("UPDATE skills SET version = ? WHERE id = ?", ("1.2.3", skill.id))
        mgr._get_conn().commit()
        upgraded = mgr.upgrade(skill.id)
        assert upgraded.version == "1.2.4"

    def test_upgrade_not_found(self, mgr):
        with pytest.raises(ValueError, match="not found"):
            mgr.upgrade(9999)

    def test_search(self, mgr):
        mgr.add_skill(name="python-sqlite-skill", summary="sqlite tutorial")
        mgr.add_skill(name="javascript-guide", summary="js tutorial")
        results = mgr.search("sqlite")
        assert len(results) == 1
        assert results[0].name == "python-sqlite-skill"

    def test_delete_skill(self, mgr):
        skill = mgr.add_skill(name="delete-me")
        ok = mgr.delete_skill(skill.id)
        assert ok is True
        assert mgr.get_skill(skill.id) is None

    def test_delete_skill_not_found(self, mgr):
        ok = mgr.delete_skill(9999)
        assert ok is False


class TestSkillEntry:
    def test_to_dict(self, mgr):
        skill = mgr.add_skill(name="dict-test", tags=["tag1"])
        d = skill.to_dict()
        assert d["name"] == "dict-test"
        assert d["tags"] == ["tag1"]
        assert d["status"] == "draft"
        assert isinstance(d["created_at"], str)

    def test_from_row(self, mgr):
        skill = mgr.add_skill(name="row-test", tags=["tag1", "tag2"])
        cur = mgr._get_conn().execute("SELECT * FROM skills WHERE id = ?", (skill.id,))
        cols = [d[0] for d in (cur.description or [])]
        row = cur.fetchone()
        rebuilt = SkillEntry.from_row(tuple(row), cols)
        assert rebuilt.name == "row-test"
        assert rebuilt.tags == ["tag1", "tag2"]