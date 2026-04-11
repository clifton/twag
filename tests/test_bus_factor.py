"""Tests for twag.bus_factor — pure-logic functions only, no git repo needed."""

from twag.bus_factor import (
    ModuleStats,
    aggregate_ownership,
    compute_repo_bus_factor,
    parse_git_blame_porcelain,
)

# --- parse_git_blame_porcelain ---


class TestParseGitBlamePorcelain:
    def test_single_author(self):
        output = (
            "abc123 1 1 1\n"
            "author Alice\n"
            "author-mail <alice@x>\n"
            "summary init\n"
            "\tline content\n"
            "abc123 2 2\n"
            "author Alice\n"
            "author-mail <alice@x>\n"
            "\tline two\n"
        )
        assert parse_git_blame_porcelain(output) == {"Alice": 2}

    def test_multiple_authors(self):
        output = "aaa 1 1 1\nauthor Alice\n\tcode\nbbb 2 2 1\nauthor Bob\n\tcode\naaa 3 3\nauthor Alice\n\tcode\n"
        result = parse_git_blame_porcelain(output)
        assert result == {"Alice": 2, "Bob": 1}

    def test_empty_output(self):
        assert parse_git_blame_porcelain("") == {}


# --- ModuleStats ---


class TestModuleStats:
    def test_bus_factor_single_author(self):
        ms = ModuleStats(path="x.py", lines_by_author={"Alice": 100})
        assert ms.bus_factor == 1
        assert ms.risk_level == "CRITICAL"
        assert ms.dominant_author == "Alice"
        assert ms.dominant_ownership_pct == 100.0

    def test_bus_factor_two_authors_unequal(self):
        ms = ModuleStats(path="x.py", lines_by_author={"Alice": 80, "Bob": 20})
        assert ms.bus_factor == 1
        assert ms.risk_level == "CRITICAL"

    def test_bus_factor_two_equal(self):
        # 50/50 split: removing one author loses exactly 50%, not >50%
        # so both are needed → bus_factor=2
        ms = ModuleStats(path="x.py", lines_by_author={"Alice": 50, "Bob": 50})
        assert ms.bus_factor == 2
        assert ms.dominant_ownership_pct == 50.0

    def test_bus_factor_three_equal(self):
        ms = ModuleStats(path="x.py", lines_by_author={"A": 34, "B": 33, "C": 33})
        assert ms.bus_factor == 2
        assert ms.risk_level == "HIGH"

    def test_bus_factor_many_authors(self):
        ms = ModuleStats(
            path="x.py",
            lines_by_author={"A": 20, "B": 20, "C": 20, "D": 20, "E": 20},
        )
        assert ms.bus_factor == 3
        assert ms.risk_level == "MEDIUM"

    def test_bus_factor_low_risk(self):
        ms = ModuleStats(
            path="x.py",
            lines_by_author={"A": 10, "B": 10, "C": 10, "D": 10, "E": 10, "F": 10},
        )
        assert ms.bus_factor == 4
        assert ms.risk_level == "LOW"

    def test_empty(self):
        ms = ModuleStats(path="x.py")
        assert ms.bus_factor == 0
        assert ms.risk_level == "N/A"
        assert ms.dominant_author is None
        assert ms.dominant_ownership_pct == 0.0
        assert ms.total_lines == 0


# --- aggregate_ownership ---


class TestAggregateOwnership:
    def test_directory_aggregation(self):
        file_stats = {
            "src/a.py": {"Alice": 50, "Bob": 10},
            "src/b.py": {"Alice": 20, "Carol": 30},
        }
        result = aggregate_ownership(file_stats)

        # Per-file entries exist
        assert "src/a.py" in result
        assert result["src/a.py"].total_lines == 60

        # Directory aggregated
        assert "src" in result
        assert result["src"].lines_by_author["Alice"] == 70
        assert result["src"].lines_by_author["Bob"] == 10
        assert result["src"].lines_by_author["Carol"] == 30
        assert result["src"].total_lines == 110

    def test_root_files(self):
        file_stats = {"README.md": {"Alice": 10}}
        result = aggregate_ownership(file_stats)
        assert "(root)" in result
        assert result["(root)"].total_lines == 10

    def test_empty(self):
        result = aggregate_ownership({})
        assert result == {}


# --- compute_repo_bus_factor ---


class TestComputeRepoBusFactor:
    def test_single_owner(self):
        file_stats = {
            "a.py": {"Alice": 100},
            "b.py": {"Alice": 50},
        }
        repo = compute_repo_bus_factor(file_stats)
        assert repo.bus_factor == 1
        assert repo.dominant_author == "Alice"
        assert repo.total_lines == 150

    def test_mixed_owners(self):
        file_stats = {
            "a.py": {"Alice": 40, "Bob": 60},
            "b.py": {"Carol": 50},
        }
        repo = compute_repo_bus_factor(file_stats)
        assert repo.total_lines == 150
        assert repo.dominant_author == "Bob"
        # Bob=60, Alice=40, Carol=50 → sorted desc: 60,50,40
        # 60 > 75? no. 60+50=110 > 75? yes → bus_factor=2
        assert repo.bus_factor == 2

    def test_empty(self):
        repo = compute_repo_bus_factor({})
        assert repo.bus_factor == 0
        assert repo.total_lines == 0
        assert repo.risk_level == "N/A"
