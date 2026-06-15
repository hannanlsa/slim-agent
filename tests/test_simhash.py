"""Tests for simhash module."""

import pytest

from slim_agent.slim_reducer.simhash import (
    _ngrams,
    hamming,
    simhash,
    simhash_similarity,
)


class TestNgrams:
    def test_english_basic(self):
        grams = _ngrams("hello world", n=4)
        assert grams[0] == "hell"
        assert grams[-1] == "orld"

    def test_chinese(self):
        # 4-gram of "JSON解析工具" → 4-grams of normalised text
        grams = _ngrams("JSON解析工具", n=4)
        assert "jso" not in grams  # n=4, so jso is partial
        assert "json" in grams
        assert "son解析" in grams or "on解析" in grams

    def test_short_text(self):
        # text shorter than n returns the whole string
        assert _ngrams("hi", n=4) == ["hi"]

    def test_empty(self):
        assert _ngrams("", n=4) == []

    def test_case_normalisation(self):
        assert _ngrams("Hello World") == _ngrams("hello world")


class TestSimhash:
    def test_identical_text_same_hash(self):
        a = simhash("fetch web page content")
        b = simhash("fetch web page content")
        assert a == b

    def test_similar_text_close_hash(self):
        a = simhash("web page fetching tool")
        b = simhash("web page fetching library")
        # 4-grams shared → hamming distance should be small
        # Empirically: 17 bits different = ~73% similar
        assert hamming(a, b) < 20

    def test_different_text_far_hash(self):
        a = simhash("python web scraping")
        b = simhash("rust systems programming")
        # 4-grams share little → hamming > 25
        assert hamming(a, b) > 25

    def test_chinese_similar(self):
        a = simhash("JSON解析工具")
        b = simhash("JSON解析库")
        # CJK 4-grams share a lot if substring matches
        assert hamming(a, b) < 20

    def test_chinese_different(self):
        a = simhash("数据读取器")
        b = simhash("网页抓取")
        # Completely different CJK strings
        assert hamming(a, b) > 25


class TestSimilarity:
    def test_identical(self):
        h = simhash("hello world")
        assert simhash_similarity(h, h) == 1.0

    def test_different(self):
        a = simhash("alpha beta gamma")
        b = simhash("delta epsilon zeta")
        assert simhash_similarity(a, b) < 0.7

    def test_range(self):
        a = simhash("test one")
        b = simhash("test two")
        s = simhash_similarity(a, b)
        assert 0.0 <= s <= 1.0

    def test_similar_above_threshold(self):
        """Helper for reducer integration: similar texts must score > 0.65."""
        a = simhash("web page fetching tool")
        b = simhash("web page fetching library")
        assert simhash_similarity(a, b) > 0.65

    def test_different_below_threshold(self):
        """Helper for reducer integration: unrelated texts must score < 0.65."""
        a = simhash("python web scraping")
        b = simhash("rust systems programming")
        assert simhash_similarity(a, b) < 0.65
