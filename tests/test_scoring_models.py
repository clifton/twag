"""Tests for twag.models.scoring — field validators for clamping."""

from twag.models.scoring import ActionableItem, TriageResult


class TestClampScore:
    def test_valid_score_unchanged(self):
        r = TriageResult(tweet_id="1", score=5.0)
        assert r.score == 5.0

    def test_zero_score(self):
        r = TriageResult(tweet_id="1", score=0.0)
        assert r.score == 0.0

    def test_max_score(self):
        r = TriageResult(tweet_id="1", score=10.0)
        assert r.score == 10.0

    def test_negative_clamped_to_zero(self):
        r = TriageResult(tweet_id="1", score=-5.0)
        assert r.score == 0.0

    def test_over_max_clamped_to_ten(self):
        r = TriageResult(tweet_id="1", score=15.0)
        assert r.score == 10.0

    def test_string_coerced_to_float(self):
        r = TriageResult(tweet_id="1", score="7.5")
        assert r.score == 7.5


class TestClampConfidence:
    def test_valid_confidence_unchanged(self):
        a = ActionableItem(action="buy", confidence=0.8)
        assert a.confidence == 0.8

    def test_zero_confidence(self):
        a = ActionableItem(action="buy", confidence=0.0)
        assert a.confidence == 0.0

    def test_max_confidence(self):
        a = ActionableItem(action="buy", confidence=1.0)
        assert a.confidence == 1.0

    def test_negative_clamped_to_zero(self):
        a = ActionableItem(action="buy", confidence=-0.5)
        assert a.confidence == 0.0

    def test_over_max_clamped_to_one(self):
        a = ActionableItem(action="buy", confidence=1.5)
        assert a.confidence == 1.0

    def test_default_confidence_is_zero(self):
        a = ActionableItem(action="buy")
        assert a.confidence == 0.0
