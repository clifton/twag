"""Tests for bus factor analysis."""

from unittest.mock import patch

from twag.bus_factor import FileOwnership, _compute_bus_factor, analyze_repo, blame_file


class TestFileOwnership:
    def test_top_author_pct(self):
        fo = FileOwnership(path="a.py", total_lines=100, authors={"Alice": 80, "Bob": 20})
        assert fo.top_author_pct == 80.0

    def test_top_author_pct_empty(self):
        fo = FileOwnership(path="a.py", total_lines=0, authors={})
        assert fo.top_author_pct == 0.0


class TestComputeBusFactor:
    def test_single_author(self):
        assert _compute_bus_factor({"Alice": 100}, 100) == 1

    def test_two_equal_authors(self):
        # Neither alone exceeds 50%, so bus factor is 2
        assert _compute_bus_factor({"Alice": 50, "Bob": 50}, 100) == 2

    def test_three_authors_uneven(self):
        # Alice has 40, Bob 35, Carol 25 — need Alice+Bob to cross 50%
        assert _compute_bus_factor({"Alice": 40, "Bob": 35, "Carol": 25}, 100) == 2

    def test_empty(self):
        assert _compute_bus_factor({}, 0) == 0


class TestBlameFile:
    @patch("twag.bus_factor.subprocess.run")
    def test_successful_blame(self, mock_run):
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = (
            "abc123 1 1 1\nauthor Alice\n\tcode line\n"
            "def456 2 2 1\nauthor Bob\n\tcode line\n"
            "ghi789 3 3 1\nauthor Alice\n\tcode line\n"
        )
        result = blame_file("/repo", "test.py")
        assert result == {"Alice": 2, "Bob": 1}

    @patch("twag.bus_factor.subprocess.run")
    def test_binary_file_returns_empty(self, mock_run):
        mock_run.return_value.returncode = 128
        mock_run.return_value.stdout = ""
        result = blame_file("/repo", "image.png")
        assert result == {}


class TestAnalyzeRepo:
    @patch("twag.bus_factor.blame_file")
    @patch("twag.bus_factor.git_tracked_files")
    def test_basic_analysis(self, mock_files, mock_blame):
        mock_files.return_value = ["src/a.py", "src/b.py", "README.md"]
        mock_blame.side_effect = [
            {"Alice": 80, "Bob": 20},
            {"Alice": 10, "Bob": 40},
            {"Alice": 5},
        ]
        report = analyze_repo("/repo")
        assert report["bus_factor"] == 1
        assert report["total_files"] == 3
        assert report["unique_authors"] == 2
        assert report["total_lines"] == 155
        assert len(report["high_risk_files"]) >= 1

    @patch("twag.bus_factor.blame_file")
    @patch("twag.bus_factor.git_tracked_files")
    def test_empty_repo(self, mock_files, mock_blame):
        mock_files.return_value = []
        report = analyze_repo("/repo")
        assert report["bus_factor"] == 0
        assert report["total_files"] == 0

    @patch("twag.bus_factor.blame_file")
    @patch("twag.bus_factor.git_tracked_files")
    def test_skips_binary_files(self, mock_files, mock_blame):
        mock_files.return_value = ["code.py", "image.png"]
        mock_blame.side_effect = [{"Alice": 50}, {}]
        report = analyze_repo("/repo")
        assert report["total_files"] == 1
