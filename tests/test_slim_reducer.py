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
    return SlimReducer(mgr)  # threshold now in registry (default 0.3)


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
        # Skills with very little overlap — longer summaries avoid 4-gram false positives
        a = mgr.add_skill(name="skill-a", summary="python web framework documentation", tags=["python"])
        b = mgr.add_skill(name="skill-b", summary="rust embedded systems compilation", tags=["rust"])
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

    def test_scan_simhash_cjk(self, reducer, mgr):
        """SimHash should catch CJK near-duplicates that word-Jaccard misses."""
        a = mgr.add_skill(name="json工具", summary="JSON解析工具用于处理数据", tags=["data"])
        b = mgr.add_skill(name="json库", summary="JSON解析库用于处理数据", tags=["data"])
        mgr.activate(a.id)
        mgr.activate(b.id)
        report = reducer.scan_skills()
        assert report.has_overlaps is True
        # SimHash signal should fire even though word-Jaccard is 0 (no shared space-separated tokens)
        assert any("simhash" in s.reason for s in report.suggestions)

    def test_scan_simhash_paraphrase(self, reducer, mgr):
        """SimHash catches paraphrases that share char n-grams but differ in word order."""
        a = mgr.add_skill(name="fetch-a", summary="fetch web pages and parse html", tags=["misc"])
        b = mgr.add_skill(name="fetch-b", summary="parse html and fetch web pages", tags=["misc"])
        mgr.activate(a.id)
        mgr.activate(b.id)
        report = reducer.scan_skills()
        assert report.has_overlaps is True

    def test_scan_reason_lists_signals(self, reducer, mgr):
        """Reason field should enumerate all fired signals."""
        a = mgr.add_skill(name="overlap-a", summary="web fetching tool", tags=["web"])
        b = mgr.add_skill(name="overlap-b", summary="web fetching lib", tags=["web"])
        mgr.activate(a.id)
        mgr.activate(b.id)
        report = reducer.scan_skills()
        assert report.has_overlaps is True
        reason = report.suggestions[0].reason
        assert "tag_jaccard" in reason


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


class TestBM25:
    """Tests for BM25 keyword matching signal."""

    def test_from_skills_empty(self):
        from slim_agent.slim_reducer.bm25 import BM25Index
        idx = BM25Index.from_skills([])
        assert idx.total_docs == 0

    def test_from_skills_basic(self):
        from slim_agent.slim_reducer.bm25 import BM25Index

        class FakeSkill:
            def __init__(self, sid, summary):
                self.id = sid
                self.summary = summary

        skills = [
            FakeSkill(1, "python web scraping tool"),
            FakeSkill(2, "python web fetching library"),
            FakeSkill(3, "rust systems programming"),
        ]
        idx = BM25Index.from_skills(skills)
        assert idx.total_docs == 3
        assert idx.avg_doc_len > 0
        # python web 应该在 doc 1 和 2 中出现
        assert idx.df["python"] == 2
        assert idx.df["rust"] == 1

    def test_score_pair_similar(self):
        from slim_agent.slim_reducer.bm25 import BM25Index

        class FakeSkill:
            def __init__(self, sid, summary):
                self.id = sid
                self.summary = summary

        skills = [
            FakeSkill(1, "web page fetching tool for scraping"),
            FakeSkill(2, "web page fetching library for data extraction"),
            FakeSkill(3, "cooking recipes and meal planning"),
        ]
        idx = BM25Index.from_skills(skills)
        sim_ab = idx.score_pair(1, 2)  # 相似
        sim_ac = idx.score_pair(1, 3)  # 不相似
        assert sim_ab > sim_ac

    def test_score_pair_returns_zero_for_missing(self):
        from slim_agent.slim_reducer.bm25 import BM25Index
        idx = BM25Index.from_skills([])
        assert idx.score_pair(999, 888) == 0.0


class TestRRF:
    """Tests for RRF score fusion."""

    def test_rrf_combine_basic(self):
        from slim_agent.slim_reducer.rrf import rrf_combine
        signals = {
            (1, 2): [{'name': 'tag', 'score': 0.5, 'weight': 1.0}],
            (3, 4): [{'name': 'tag', 'score': 0.8, 'weight': 1.0}],
        }
        result = rrf_combine(signals)
        assert (1, 2) in result
        assert (3, 4) in result
        # 更多/更高权重信号 → 更高 RRF 分数
        assert result[(3, 4)] > 0

    def test_rrf_combine_multiple_signals(self):
        from slim_agent.slim_reducer.rrf import rrf_combine
        signals = {
            (1, 2): [
                {'name': 'tag', 'score': 0.5, 'weight': 1.0},
                {'name': 'bm25', 'score': 0.7, 'weight': 1.5},
                {'name': 'simhash', 'score': 0.9, 'weight': 1.0},
            ],
            (3, 4): [
                {'name': 'tag', 'score': 0.5, 'weight': 1.0},
            ],
        }
        result = rrf_combine(signals)
        # 3 信号 > 1 信号 → 更高 RRF 分数
        assert result[(1, 2)] > result[(3, 4)]

    def test_rrf_combine_empty(self):
        from slim_agent.slim_reducer.rrf import rrf_combine
        assert rrf_combine({}) == {}

    def test_rrf_combine_pairs_ranks(self):
        from slim_agent.slim_reducer.rrf import rrf_combine_pairs
        pairs = [
            ("a", "b", [{'name': 's1', 'score': 0.9, 'weight': 1.0}]),
            ("c", "d", [{'name': 's1', 'score': 0.9, 'weight': 1.0},
                         {'name': 's2', 'score': 0.8, 'weight': 1.0}]),
        ]
        ranked = rrf_combine_pairs(pairs)
        assert len(ranked) == 2
        # 2 信号应该排在 1 信号前面
        assert ranked[0][0] > ranked[1][0]