"""Vision fetcher must reject non-http(s) URLs before issuing any HTTP call.

The image_url passed to the vision call paths can come from LLM-extracted
content; without a scheme allowlist an attacker could redirect us to file://,
gopher://, or link-local hosts.
"""

import pytest

from twag.scorer.llm_client import (
    UnsafeImageURLError,
    _call_anthropic_vision,
    _call_gemini_vision,
    _validate_image_url,
)


def test_validate_image_url_accepts_http():
    _validate_image_url("http://example.com/image.png")


def test_validate_image_url_accepts_https():
    _validate_image_url("https://example.com/image.png")


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "gopher://internal/",
        "ftp://example.com/image.png",
        "data:image/png;base64,AAA",
        "javascript:alert(1)",
        "ldap://internal/",
    ],
)
def test_validate_image_url_rejects_non_http_schemes(url):
    with pytest.raises(UnsafeImageURLError):
        _validate_image_url(url)


def test_validate_image_url_rejects_empty():
    with pytest.raises(UnsafeImageURLError):
        _validate_image_url("")


def test_validate_image_url_rejects_missing_host():
    with pytest.raises(UnsafeImageURLError):
        _validate_image_url("http:///path")


def test_gemini_vision_rejects_file_url_without_http_call(monkeypatch):
    """The httpx.get call must NOT happen for disallowed schemes."""
    called = {"hit": False}

    def fake_get(*args, **kwargs):
        called["hit"] = True
        raise AssertionError("httpx.get must not be called for disallowed schemes")

    import httpx

    monkeypatch.setattr(httpx, "get", fake_get)

    with pytest.raises(UnsafeImageURLError):
        _call_gemini_vision("model", "file:///etc/passwd", "describe")
    assert called["hit"] is False


def test_anthropic_vision_rejects_file_url_without_api_call(monkeypatch):
    """The Anthropic client must NOT be constructed for disallowed schemes."""
    constructed = {"hit": False}

    def fake_client(*args, **kwargs):
        constructed["hit"] = True
        raise AssertionError("anthropic client must not be constructed for disallowed schemes")

    monkeypatch.setattr("twag.scorer.llm_client.get_anthropic_client", fake_client)

    with pytest.raises(UnsafeImageURLError):
        _call_anthropic_vision("model", "file:///etc/passwd", "describe")
    assert constructed["hit"] is False


def test_gemini_vision_disables_redirect_following(monkeypatch):
    """Even with a valid http(s) URL, redirects must not be followed."""
    captured = {}

    class FakeResponse:
        content: bytes = b"fake-bytes"
        headers: dict = {"content-type": "image/png"}  # noqa: RUF012

        def raise_for_status(self):
            pass

    def fake_get(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return FakeResponse()

    import httpx

    monkeypatch.setattr(httpx, "get", fake_get)

    class FakeGeminiClient:
        class models:
            @staticmethod
            def generate_content(**kwargs):
                class R:
                    text = "ok"

                return R()

    def make_client():
        return FakeGeminiClient()

    monkeypatch.setattr("twag.scorer.llm_client.get_gemini_client", make_client)

    _call_gemini_vision("model", "https://example.com/img.png", "describe")
    assert captured["kwargs"].get("follow_redirects") is False
