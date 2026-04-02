"""Tests for twag.text_utils — surrogate replacement and recursive sanitization."""

from twag.text_utils import replace_lone_surrogates, sanitize_nested_strings, sanitize_text


def test_replace_lone_surrogates_no_surrogates():
    assert replace_lone_surrogates("hello world") == "hello world"


def test_replace_lone_surrogates_empty_string():
    assert replace_lone_surrogates("") == ""


def test_replace_lone_surrogates_replaces_lone_high_surrogate():
    text = "before\ud800after"
    result = replace_lone_surrogates(text)
    assert result == "before\ufffdafter"


def test_replace_lone_surrogates_replaces_lone_low_surrogate():
    text = "x\udfffx"
    result = replace_lone_surrogates(text)
    assert result == "x\ufffdx"


def test_replace_lone_surrogates_multiple():
    text = "\ud800\udfff"
    result = replace_lone_surrogates(text)
    assert result == "\ufffd\ufffd"


def test_sanitize_text_none():
    assert sanitize_text(None) is None


def test_sanitize_text_clean_string():
    assert sanitize_text("clean") == "clean"


def test_sanitize_text_with_surrogate():
    assert sanitize_text("a\ud800b") == "a\ufffdb"


def test_sanitize_nested_strings_plain_string():
    assert sanitize_nested_strings("hello") == "hello"


def test_sanitize_nested_strings_dict():
    data = {"key": "val\ud800ue", "num": 42}
    result = sanitize_nested_strings(data)
    assert result == {"key": "val\ufffdue", "num": 42}


def test_sanitize_nested_strings_list():
    data = ["ok", "bad\ud800"]
    result = sanitize_nested_strings(data)
    assert result == ["ok", "bad\ufffd"]


def test_sanitize_nested_strings_tuple():
    data = ("a\ud800", "b")
    result = sanitize_nested_strings(data)
    assert result == ("a\ufffd", "b")


def test_sanitize_nested_strings_nested_dict_in_list():
    data = [{"inner": "x\ud800y"}]
    result = sanitize_nested_strings(data)
    assert result == [{"inner": "x\ufffdy"}]


def test_sanitize_nested_strings_non_string_passthrough():
    assert sanitize_nested_strings(42) == 42
    assert sanitize_nested_strings(None) is None
    assert sanitize_nested_strings(3.14) == 3.14
