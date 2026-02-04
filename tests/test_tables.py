"""Tests for table extraction and rendering."""

import html

import pytest

from twag.tables import should_show_inline, table_to_markdown
from twag.scorer import MediaAnalysisResult
from twag.web.app import create_app


def safe_unescape(s):
    """Safe unescape that handles None - mirrors the Jinja filter."""
    return html.unescape(s) if s else s


class TestHtmlEntityUnescaping:
    """Test that HTML entities are properly decoded."""

    def test_unescape_ampersand(self):
        assert html.unescape("P&amp;L") == "P&L"

    def test_unescape_angle_brackets(self):
        assert html.unescape("&lt;tag&gt;") == "<tag>"

    def test_unescape_multiple_entities(self):
        assert html.unescape("A &amp; B &lt; C") == "A & B < C"

    def test_unescape_no_entities(self):
        assert html.unescape("plain text") == "plain text"

    def test_safe_unescape_with_none(self):
        """Test that safe_unescape handles None gracefully."""
        assert safe_unescape(None) is None

    def test_safe_unescape_with_empty_string(self):
        """Test that safe_unescape handles empty string."""
        assert safe_unescape("") == ""

    def test_safe_unescape_normal(self):
        """Test that safe_unescape works normally."""
        assert safe_unescape("P&amp;L") == "P&L"


class TestTableDataStructure:
    """Test valid table data structures."""

    def test_table_schema_valid(self):
        table = {
            "columns": ["A", "B"],
            "rows": [["1", "2"], ["3", "4"]],
            "summary": "Test table",
        }
        assert len(table["columns"]) == 2
        assert len(table["rows"]) == 2

    def test_table_empty_rows(self):
        table = {"columns": ["A"], "rows": []}
        assert len(table["rows"]) == 0

    def test_table_with_tickers(self):
        table = {
            "columns": ["Ticker", "Price"],
            "rows": [["MSFT", "$400"]],
            "tickers": ["MSFT"],
        }
        assert table["tickers"] == ["MSFT"]


class TestTableToMarkdown:
    """Test markdown output formatting."""

    def test_basic_table(self):
        table = {"columns": ["A", "B"], "rows": [["1", "2"]]}
        md = table_to_markdown(table)
        assert "A" in md
        assert "B" in md
        assert "1" in md
        assert "2" in md
        assert "|" in md  # Uses pipe-delimited format

    def test_alignment_consistent(self):
        table = {
            "columns": ["Name", "Value"],
            "rows": [["Short", "1"], ["Longer Name", "123"]],
        }
        md = table_to_markdown(table)
        lines = md.strip().split("\n")
        # Header, separator, and data rows
        assert len(lines) == 4

    def test_empty_table(self):
        table = {"columns": [], "rows": []}
        md = table_to_markdown(table)
        assert md == ""

    def test_financial_data(self):
        table = {
            "columns": ["Investor", "Capital In", "Current Value", "P&L"],
            "rows": [
                ["Microsoft", "$13B", "$236B", "$223B"],
                ["Amazon", "$4B", "$8B", "$4B"],
            ],
        }
        md = table_to_markdown(table)
        assert "Microsoft" in md
        assert "$223B" in md
        assert "P&L" in md


class TestTableRowCountToggle:
    """Test inline vs toggle display logic."""

    def test_short_table_shows_inline(self):
        table = {"columns": ["A"], "rows": [["1"]] * 5}
        assert should_show_inline(table) is True

    def test_exactly_10_rows_shows_inline(self):
        table = {"columns": ["A"], "rows": [["1"]] * 10}
        assert should_show_inline(table) is True

    def test_long_table_shows_toggle(self):
        table = {"columns": ["A"], "rows": [["1"]] * 15}
        assert should_show_inline(table) is False

    def test_custom_threshold(self):
        table = {"columns": ["A"], "rows": [["1"]] * 5}
        assert should_show_inline(table, threshold=3) is False
        assert should_show_inline(table, threshold=5) is True

    def test_empty_rows(self):
        table = {"columns": ["A"], "rows": []}
        assert should_show_inline(table) is True


class TestMediaAnalysisResultTable:
    """Test that table images get kind='table'."""

    def test_table_kind(self):
        result = MediaAnalysisResult(
            kind="table",
            short_description="Financial data table",
            prose_text="",
            prose_summary="",
            chart={},
            table={"columns": ["A"], "rows": [["1"]]},
        )
        assert result.kind == "table"
        assert result.table["columns"] == ["A"]

    def test_table_with_full_data(self):
        result = MediaAnalysisResult(
            kind="table",
            short_description="Investment returns table",
            prose_text="",
            prose_summary="",
            chart={
                "type": "",
                "description": "",
                "insight": "",
                "implication": "",
                "tickers": [],
            },
            table={
                "title": "OpenAI Investment Returns",
                "description": "Shows investor capital and current value",
                "columns": ["Investor", "Capital In", "Current Value", "P&L"],
                "rows": [
                    ["Microsoft", "$13B", "$236B", "$223B"],
                    ["Amazon", "$4B", "$8B", "$4B"],
                ],
                "summary": "Microsoft leads with $223B P&L. Total investor returns exceed $230B.",
                "tickers": ["MSFT", "AMZN"],
            },
        )
        assert result.kind == "table"
        assert len(result.table["columns"]) == 4
        assert len(result.table["rows"]) == 2
        assert result.table["tickers"] == ["MSFT", "AMZN"]


class TestWebAppUnescapeFilter:
    """Test the web app's unescape filter handles edge cases."""

    def test_unescape_filter_handles_none(self):
        """Test that the Jinja unescape filter handles None values."""
        app = create_app()
        unescape = app.state.templates.env.filters["unescape"]
        assert unescape(None) is None

    def test_unescape_filter_handles_empty(self):
        """Test that the Jinja unescape filter handles empty strings."""
        app = create_app()
        unescape = app.state.templates.env.filters["unescape"]
        assert unescape("") == ""

    def test_unescape_filter_decodes_entities(self):
        """Test that the Jinja unescape filter decodes HTML entities."""
        app = create_app()
        unescape = app.state.templates.env.filters["unescape"]
        assert unescape("P&amp;L") == "P&L"
        assert unescape("&lt;tag&gt;") == "<tag>"
