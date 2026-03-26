"""Tests for twag.text_utils — surrogate replacement and nested sanitization."""

from twag.text_utils import replace_lone_surrogates, sanitize_nested_strings, sanitize_text


class TestReplaceLoneSurrogates:
    def test_clean_string_unchanged(self):
        assert replace_lone_surrogates("hello world") == "hello world"

    def test_empty_string(self):
        assert replace_lone_surrogates("") == ""

    def test_lone_surrogate_replaced(self):
        # \ud800 is a lone high surrogate
        text = "before\ud800after"
        result = replace_lone_surrogates(text)
        assert "\ud800" not in result
        assert "\ufffd" in result
        assert result == "before\ufffdafter"

    def test_low_surrogate_replaced(self):
        text = "test\udfffend"
        result = replace_lone_surrogates(text)
        assert result == "test\ufffdend"

    def test_multiple_surrogates(self):
        text = "\ud800\ud801normal\udfff"
        result = replace_lone_surrogates(text)
        assert result == "\ufffd\ufffdnormal\ufffd"


class TestSanitizeText:
    def test_none_returns_none(self):
        assert sanitize_text(None) is None

    def test_clean_string(self):
        assert sanitize_text("clean") == "clean"

    def test_surrogate_cleaned(self):
        assert "\ufffd" in sanitize_text("has\ud800surrogate")


class TestSanitizeNestedStrings:
    def test_plain_string(self):
        assert sanitize_nested_strings("hello") == "hello"

    def test_nested_dict(self):
        data = {"key": "val\ud800ue", "nested": {"inner": "ok"}}
        result = sanitize_nested_strings(data)
        assert result["key"] == "val\ufffdue"
        assert result["nested"]["inner"] == "ok"

    def test_list(self):
        data = ["clean", "has\ud800bad"]
        result = sanitize_nested_strings(data)
        assert result == ["clean", "has\ufffdbad"]

    def test_tuple(self):
        data = ("a\ud800b",)
        result = sanitize_nested_strings(data)
        assert result == ("a\ufffdb",)

    def test_non_string_passthrough(self):
        assert sanitize_nested_strings(42) == 42
        assert sanitize_nested_strings(None) is None
        assert sanitize_nested_strings(3.14) == 3.14

    def test_mixed_nested(self):
        data = {"items": [{"text": "ok"}, {"text": "bad\ud800char"}], "count": 2}
        result = sanitize_nested_strings(data)
        assert result["items"][1]["text"] == "bad\ufffdchar"
        assert result["count"] == 2

    def test_dict_keys_sanitized(self):
        data = {"key\ud800bad": "value"}
        result = sanitize_nested_strings(data)
        assert "key\ufffdbad" in result
