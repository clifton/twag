"""Tests for bus-factor analysis core logic."""

from __future__ import annotations

from twag.bus_factor import (
    ModuleStats,
    aggregate_ownership,
    compute_repo_bus_factor,
    parse_git_blame_porcelain,
)


class TestParseGitBlamePorcelain:
    def test_single_author(self):
        output = (
            "abc123 1 1 1\n"
            "author Alice\n"
            "author-mail <alice@example.com>\n"
            "summary init\n"
            "filename foo.py\n"
            "\tprint('hello')\n"
        )
        result = parse_git_blame_porcelain(output)
        assert result == [("Alice", 1)]

    def test_multiple_authors(self):
        output = (
            "abc123 1 1 1\n"
            "author Alice\n"
            "summary init\n"
            "filename foo.py\n"
            "\tline1\n"
            "def456 2 2 1\n"
            "author Bob\n"
            "summary update\n"
            "filename foo.py\n"
            "\tline2\n"
        )
        result = parse_git_blame_porcelain(output)
        assert result == [("Alice", 1), ("Bob", 1)]

    def test_empty_output(self):
        assert parse_git_blame_porcelain("") == []


class TestModuleStats:
    def test_bus_factor_single_author(self):
        stats = ModuleStats(path="mod/", total_lines=100, author_lines={"Alice": 100})
        assert stats.bus_factor == 1
        assert stats.risk_level == "HIGH"

    def test_bus_factor_two_equal_authors(self):
        stats = ModuleStats(path="mod/", total_lines=100, author_lines={"Alice": 50, "Bob": 50})
        # Need 1 author to exceed 50% — one author has exactly 50 which is not >50
        # So need both => bus factor 2
        assert stats.bus_factor == 2
        assert stats.risk_level == "MEDIUM"

    def test_bus_factor_dominant_plus_minor(self):
        stats = ModuleStats(
            path="mod/",
            total_lines=100,
            author_lines={"Alice": 80, "Bob": 15, "Carol": 5},
        )
        assert stats.bus_factor == 1
        assert stats.risk_level == "HIGH"

    def test_bus_factor_three_equal_authors(self):
        stats = ModuleStats(
            path="mod/",
            total_lines=99,
            author_lines={"Alice": 33, "Bob": 33, "Carol": 33},
        )
        # Top author has 33, need >49.5 => need 2 authors (33+33=66)
        assert stats.bus_factor == 2

    def test_bus_factor_well_distributed(self):
        stats = ModuleStats(
            path="mod/",
            total_lines=100,
            author_lines={"Alice": 20, "Bob": 20, "Carol": 20, "Dave": 20, "Eve": 20},
        )
        # Need >50 lines => 3 authors (20+20+20=60)
        assert stats.bus_factor == 3
        assert stats.risk_level == "LOW"

    def test_bus_factor_empty(self):
        stats = ModuleStats(path="mod/", total_lines=0, author_lines={})
        assert stats.bus_factor == 0

    def test_dominant_author(self):
        stats = ModuleStats(path="mod/", total_lines=100, author_lines={"Alice": 70, "Bob": 30})
        author, pct = stats.dominant_author
        assert author == "Alice"
        assert pct == 70.0


class TestAggregateOwnership:
    def test_aggregates_to_directory(self):
        blame_data = {
            "src/foo.py": [("Alice", 1)] * 10,
            "src/bar.py": [("Bob", 1)] * 5,
            "lib/baz.py": [("Alice", 1)] * 8,
        }
        modules = aggregate_ownership(blame_data)

        assert "src/" in modules
        src = modules["src/"]
        assert src.total_lines == 15
        assert src.author_lines["Alice"] == 10
        assert src.author_lines["Bob"] == 5

        assert "lib/" in modules
        lib = modules["lib/"]
        assert lib.total_lines == 8
        assert lib.author_lines["Alice"] == 8

    def test_per_file_stats(self):
        blame_data = {
            "src/foo.py": [("Alice", 1)] * 10 + [("Bob", 1)] * 5,
        }
        modules = aggregate_ownership(blame_data)
        assert "src/foo.py" in modules
        f = modules["src/foo.py"]
        assert f.total_lines == 15
        assert f.bus_factor == 1  # Alice has 10/15 > 50%

    def test_empty_blame_data(self):
        modules = aggregate_ownership({})
        assert modules == {}


class TestComputeRepoBusFactor:
    def test_single_owner_repo(self):
        modules = {
            "src/": ModuleStats(path="src/", total_lines=100, author_lines={"Alice": 100}),
            "tests/": ModuleStats(path="tests/", total_lines=50, author_lines={"Alice": 50}),
        }
        assert compute_repo_bus_factor(modules) == 1

    def test_mixed_ownership(self):
        modules = {
            "src/": ModuleStats(path="src/", total_lines=100, author_lines={"Alice": 60, "Bob": 40}),
            "tests/": ModuleStats(
                path="tests/",
                total_lines=100,
                author_lines={"Alice": 34, "Bob": 33, "Carol": 33},
            ),
        }
        # src/ bus factor = 1 (Alice > 50%), tests/ bus factor = 2
        # repo bus factor = min = 1
        assert compute_repo_bus_factor(modules) == 1

    def test_empty_modules(self):
        assert compute_repo_bus_factor({}) == 0
