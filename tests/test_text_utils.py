"""Tests for twag.text_utils — surrogate sanitization."""

from twag.text_utils import replace_lone_surrogates, sanitize_nested_strings, sanitize_text


class TestReplaceLoneSurrogates:
    def test_empty_string(self):
        assert replace_lone_surrogates("") == ""

    def test_clean_string(self):
        assert replace_lone_surrogates("hello world") == "hello world"

    def test_lone_high_surrogate(self):
        # U+D800 is a lone high surrogate
        text = "before\ud800after"
        result = replace_lone_surrogates(text)
        assert result == "before\ufffdafter"

    def test_lone_low_surrogate(self):
        text = "before\udc00after"
        result = replace_lone_surrogates(text)
        assert result == "before\ufffdafter"

    def test_multiple_surrogates(self):
        text = "\ud800test\udbff\udc00end"
        result = replace_lone_surrogates(text)
        assert "\ud800" not in result
        assert "\udbff" not in result
        assert "\udc00" not in result
        assert "test" in result
        assert "end" in result

    def test_no_surrogates_returns_original(self):
        text = "normal ascii + émojis 🎉"
        assert replace_lone_surrogates(text) is text  # same object


class TestSanitizeText:
    def test_none_returns_none(self):
        assert sanitize_text(None) is None

    def test_clean_string(self):
        assert sanitize_text("hello") == "hello"

    def test_surrogate_replaced(self):
        assert sanitize_text("x\ud800y") == "x\ufffdy"


class TestSanitizeNestedStrings:
    def test_plain_string(self):
        assert sanitize_nested_strings("hello\ud800") == "hello\ufffd"

    def test_integer_passthrough(self):
        assert sanitize_nested_strings(42) == 42

    def test_none_passthrough(self):
        assert sanitize_nested_strings(None) is None

    def test_list(self):
        result = sanitize_nested_strings(["ok", "bad\ud800"])
        assert result == ["ok", "bad\ufffd"]

    def test_tuple(self):
        result = sanitize_nested_strings(("ok", "bad\ud800"))
        assert result == ("ok", "bad\ufffd")
        assert isinstance(result, tuple)

    def test_dict_keys_and_values(self):
        result = sanitize_nested_strings({"key\ud800": "val\udc00"})
        assert result == {"key\ufffd": "val\ufffd"}

    def test_nested_structure(self):
        data = {"a": ["x\ud800", {"b": "y\udc00"}]}
        result = sanitize_nested_strings(data)
        assert result == {"a": ["x\ufffd", {"b": "y\ufffd"}]}

    def test_empty_containers(self):
        assert sanitize_nested_strings([]) == []
        assert sanitize_nested_strings({}) == {}
        assert sanitize_nested_strings(()) == ()
