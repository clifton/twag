"""Tests for twag.text_utils — surrogate sanitization helpers."""

from twag.text_utils import replace_lone_surrogates, sanitize_nested_strings, sanitize_text


class TestReplaceLoneSurrogates:
    def test_empty_string(self):
        assert replace_lone_surrogates("") == ""

    def test_clean_string(self):
        assert replace_lone_surrogates("hello world") == "hello world"

    def test_lone_high_surrogate(self):
        s = "before\ud800after"
        result = replace_lone_surrogates(s)
        assert result == "before\ufffdafter"

    def test_lone_low_surrogate(self):
        s = "x\udfffx"
        result = replace_lone_surrogates(s)
        assert result == "x\ufffdx"

    def test_multiple_surrogates(self):
        s = "\ud800\udbff"
        result = replace_lone_surrogates(s)
        assert result == "\ufffd\ufffd"

    def test_preserves_normal_unicode(self):
        s = "café ☕ 🎉"
        assert replace_lone_surrogates(s) == s


class TestSanitizeText:
    def test_none_returns_none(self):
        assert sanitize_text(None) is None

    def test_clean_string_passthrough(self):
        assert sanitize_text("ok") == "ok"

    def test_surrogate_replaced(self):
        assert sanitize_text("a\ud800b") == "a\ufffdb"


class TestSanitizeNestedStrings:
    def test_plain_string(self):
        assert sanitize_nested_strings("a\ud800b") == "a\ufffdb"

    def test_clean_string(self):
        assert sanitize_nested_strings("hello") == "hello"

    def test_list(self):
        result = sanitize_nested_strings(["ok", "a\ud800b"])
        assert result == ["ok", "a\ufffdb"]

    def test_tuple(self):
        result = sanitize_nested_strings(("ok", "a\ud800b"))
        assert result == ("ok", "a\ufffdb")
        assert isinstance(result, tuple)

    def test_dict_keys_and_values(self):
        result = sanitize_nested_strings({"a\ud800b": "c\ud800d"})
        assert result == {"a\ufffdb": "c\ufffdd"}

    def test_nested_structure(self):
        data = {"items": [{"text": "x\ud800y"}]}
        result = sanitize_nested_strings(data)
        assert result == {"items": [{"text": "x\ufffdy"}]}

    def test_non_string_passthrough(self):
        assert sanitize_nested_strings(42) == 42
        assert sanitize_nested_strings(None) is None
        assert sanitize_nested_strings(3.14) == 3.14
