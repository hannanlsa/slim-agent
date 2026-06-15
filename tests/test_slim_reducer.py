"""Tests for slim_reducer module."""

import tempfile
from pathlib import Path

import pytest

from slim_agent.skill_manager import SkillManager, SkillStatus
from slim_agent.slim_reducer import MergeSuggestion, RedundancyReport, SlimReducer


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


@pytest.fixture
def reducer(mgr):
    return SlimReducer(mgr, threshold=0.3)


class TestSlimReducer:
    def test_scan_empty(self, reducer):
        report = reducer.scan_skills()
        assert report.active_skill_count == 0
        assert report.suggestions == []
        assert report.has_overlaps is False

    def test_scan_single_skill(self, reducer, mgr):
        skill = mgr.add_skill(name="solo", summary="one skill only")
        mgr.activate(skill.id)
        report = reducer.scan_skills()
        assert report.active_skill_count == 1
        assert report.suggestions == []

    def test_scan_no_overlap(self, reducer, mgr):
        a = mgr.add_skill(name="skill-a", summary="python web scraping", tags=["python", "web"])
        b = mgr.add_skill(name="skill-b", summary="rust systems programming", tags=["rust", "systems"])
        mgr.activate(a.id)
        mgr.activate(b.id)
        report = reducer.scan_skills()
        assert report.active_skill_count == 2
        assert report.suggestions == []

    def test_scan_tag_overlap(self, reducer, mgr):
        a = mgr.add_skill(name="skill-a", summary="fetch web pages", tags=["web", "fetch"])
        b = mgr.add_skill(name="skill-b", summary="fetch APIs", tags=["fetch", "api"])
        mgr.activate(a.id)
        mgr.activate(b.id)
        report = reducer.scan_skills()
        assert report.has_overlaps is True
        suggestion = report.suggestions[0]
        assert "fetch" in suggestion.shared_tags
        assert suggestion.overlap_score >= 0.3

    def test_scan_summary_overlap(self, reducer, mgr):
        a = mgr.add_skill(name="skill-a", summary="web page fetching tool", tags=["tag1"])
        b = mgr.add_skill(name="skill-b", summary="web page fetching library", tags=["tag2"])
        mgr.activate(a.id)
        mgr.activate(b.id)
        report = reducer.scan_skills()
        assert report.has_overlaps is True
        assert len(report.suggestions) == 1

    def test_scan_threshold_filters_low_overlap(self, reducer, mgr):
        # Skills with very little overlap
        a = mgr.add_skill(name="skill-a", summary="python guide", tags=["python"])
        b = mgr.add_skill(name="skill-b", summary="rust guide", tags=["rust"])
        mgr.activate(a.id)
        mgr.activate(b.id)
        report = reducer.scan_skills()
        assert report.suggestions == []

    def test_scan_only_active_skills(self, reducer, mgr):
        # Only active skills should be scanned
        draft = mgr.add_skill(name="draft-skill", summary="draft content", tags=["python", "web"])
        active = mgr.add_skill(name="active-skill", summary="active content", tags=["python", "web"])
        mgr.activate(active.id)
        report = reducer.scan_skills()
        assert report.active_skill_count == 1
        # draft should not be in suggestions
        assert not any("draft-skill" in s.skills_names for s in report.suggestions)


class TestRedundancyReport:
    def test_has_overlaps_false(self):
        report = RedundancyReport()
        assert report.has_overlaps is False

    def test_has_overlaps_true(self):
        report = RedundancyReport(
            suggestions=[
                MergeSuggestion(
                    skill_ids=[1, 2],
                    skill_names=["a", "b"],
                    shared_tags=["tag1"],
                    overlap_score=0.5,
                    reason="tag overlap",
                )
            ]
        )
        assert report.has_overlaps is True

    def test_active_skill_count(self):
        report = RedundancyReport(active_skill_count=5)
        assert report.active_skill_count == 5


class TestMergeSuggestion:
    def test_to_dict(self):
        suggestion = MergeSuggestion(
            skill_ids=[1, 2],
            skill_names=["a", "b"],
            shared_tags=["python"],
            overlap_score=0.75,
            reason="high overlap",
        )
        d = suggestion.__dict__
        assert d["skill_ids"] == [1, 2]
        assert d["overlap_score"] == 0.75