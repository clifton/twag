"""Strict subprocess client for the machine-wide charts vision service."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

CHARTS_MODEL_KEY = "charts"
CHARTS_PROVIDER = "charts"
CHARTS_TAG_FIELDS = (
    "tickers",
    "countries",
    "asset_classes",
    "fx_pairs",
    "indices",
    "concepts",
    "themes",
)


@dataclass(frozen=True)
class ChartsProcessResult:
    """Captured result from one charts child process."""

    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class ChartsAnalysis:
    """Validated charts analyze response."""

    id: str
    ext: str
    kind: str
    status: str
    tag_status: str
    title: str | None
    transcript: str | None
    insight: str | None
    caption: str | None
    tags: dict[str, list[str]]
    cdn_url: str | None
    cached: bool


class ChartsUnavailableError(RuntimeError):
    """The charts runtime could not produce a valid contract response."""

    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason


class ChartsAnalysisError(RuntimeError):
    """charts was available but returned a structured analysis failure."""

    def __init__(self, message: str, details: dict[str, Any]):
        super().__init__(message)
        self.details = details


ChartsRunner = Callable[[list[str], float], ChartsProcessResult]


def run_charts_process(
    args: list[str],
    deadline_seconds: float,
    *,
    popen_factory: Callable[..., Any] = subprocess.Popen,
) -> ChartsProcessResult:
    """Run charts without a shell, killing the child when its deadline expires."""
    try:
        process = popen_factory(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except OSError as exc:
        raise ChartsUnavailableError("spawn_failure", f"could not start charts: {exc}") from exc

    try:
        stdout, stderr = process.communicate(timeout=deadline_seconds)
    except subprocess.TimeoutExpired as exc:
        process.kill()
        process.communicate()
        raise ChartsUnavailableError(
            "deadline",
            f"charts exceeded its {deadline_seconds:g}s deadline",
        ) from exc

    return ChartsProcessResult(
        returncode=int(process.returncode),
        stdout=stdout or "",
        stderr=stderr or "",
    )


def _parse_json_object(text: str) -> dict[str, Any] | None:
    try:
        value = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def _optional_string(value: Any, field: str) -> str | None:
    if value is None or isinstance(value, str):
        return value
    raise ValueError(f"{field} must be a string or null")


def _validate_success(payload: dict[str, Any]) -> ChartsAnalysis:
    required = {
        "id",
        "ext",
        "kind",
        "status",
        "tag_status",
        "title",
        "transcript",
        "insight",
        "caption",
        "tags",
        "cdn_url",
        "cached",
    }
    missing = sorted(required.difference(payload))
    if missing:
        raise ValueError(f"missing required fields: {', '.join(missing)}")

    chart_id = payload["id"]
    if (
        not isinstance(chart_id, str)
        or len(chart_id) != 64
        or any(character not in "0123456789abcdef" for character in chart_id)
    ):
        raise ValueError("id must be a 64-character SHA-256 hex string")

    ext = payload["ext"]
    if ext not in {"png", "jpg", "webp", "gif"}:
        raise ValueError("ext is not supported by the charts contract")
    kind = payload["kind"]
    if kind not in {"chart", "table", "document", "photo", "meme", "other"}:
        raise ValueError("kind is not supported by the charts contract")
    status = payload["status"]
    if status not in {"active", "rejected"}:
        raise ValueError("status is not supported by the charts contract")
    if status == "active" and kind not in {"chart", "table", "document"}:
        raise ValueError("active results must be charts, tables, or documents")
    if status == "rejected" and kind not in {"photo", "meme", "other"}:
        raise ValueError("rejected results must be photos, memes, or other media")
    if payload["tag_status"] != "tagged":
        raise ValueError("tag_status must be tagged")
    if not isinstance(payload["cached"], bool):
        raise ValueError("cached must be a boolean")

    raw_tags = payload["tags"]
    if not isinstance(raw_tags, dict):
        raise ValueError("tags must be an object")
    tags: dict[str, list[str]] = {}
    for field in CHARTS_TAG_FIELDS:
        values = raw_tags.get(field)
        if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
            raise ValueError(f"tags.{field} must be an array of strings")
        tags[field] = [value for value in values if isinstance(value, str)]

    cdn_url = _optional_string(payload["cdn_url"], "cdn_url")
    if status == "rejected" and cdn_url is not None:
        raise ValueError("rejected results must not have a CDN URL")

    return ChartsAnalysis(
        id=chart_id,
        ext=ext,
        kind=kind,
        status=status,
        tag_status="tagged",
        title=_optional_string(payload["title"], "title"),
        transcript=_optional_string(payload["transcript"], "transcript"),
        insight=_optional_string(payload["insight"], "insight"),
        caption=_optional_string(payload["caption"], "caption"),
        tags=tags,
        cdn_url=cdn_url,
        cached=payload["cached"],
    )


def analyze_with_charts(
    input_ref: str,
    *,
    caption: str,
    executable: str = "charts",
    deadline_seconds: float = 90.0,
    runner: ChartsRunner | None = None,
) -> ChartsAnalysis:
    """Invoke and validate ``charts analyze`` according to its consumer contract."""
    args = [
        executable,
        "analyze",
        input_ref,
        "--source",
        "twitter",
        "--caption",
        caption,
        "--json",
    ]
    invoke = runner or run_charts_process
    try:
        result = invoke(args, deadline_seconds)
    except ChartsUnavailableError:
        raise
    except OSError as exc:
        raise ChartsUnavailableError("spawn_failure", f"could not start charts: {exc}") from exc

    if result.returncode != 0:
        failure = _parse_json_object(result.stderr.strip())
        if failure is None:
            raise ChartsUnavailableError(
                "invalid_contract",
                "charts failed without a valid structured error document",
            )
        message = failure.get("error")
        if not isinstance(message, str) or not message.strip():
            raise ChartsUnavailableError(
                "invalid_contract",
                "charts failure document did not contain an error string",
            )
        raise ChartsAnalysisError(message.strip(), failure)

    payload = _parse_json_object(result.stdout.strip())
    if payload is None:
        raise ChartsUnavailableError(
            "invalid_contract",
            "charts exited successfully without a JSON object on stdout",
        )
    try:
        return _validate_success(payload)
    except ValueError as exc:
        raise ChartsUnavailableError(
            "invalid_contract",
            f"charts response violated the consumer contract: {exc}",
        ) from exc
