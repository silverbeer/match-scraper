"""Unit tests for the `rankings` CLI command."""

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from typer.testing import CliRunner

from src.cli.main import app
from src.models.qop_ranking import QoPRanking, QoPSnapshot

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

runner = CliRunner()


def _make_snapshot() -> QoPSnapshot:
    """Build a minimal QoPSnapshot for use in tests."""
    return QoPSnapshot(
        detected_at=date(2026, 4, 13),
        division="Northeast",
        age_group="U14",
        scraped_at=datetime(2026, 4, 16, 10, 0, 0, tzinfo=timezone.utc),
        rankings=[
            QoPRanking(
                rank=1,
                team_name="New York City FC",
                matches_played=16,
                att_score=89.6,
                def_score=83.1,
                qop_score=87.6,
            ),
            QoPRanking(
                rank=2,
                team_name="New England Revolution",
                matches_played=15,
                att_score=78.4,
                def_score=81.2,
                qop_score=79.5,
            ),
        ],
    )


def _mock_scraper(snapshot: QoPSnapshot):
    """Return a patched MLSQoPScraper whose scrape() returns the given snapshot."""
    mock_instance = MagicMock()
    mock_instance.scrape = AsyncMock(return_value=snapshot)
    return mock_instance


# ---------------------------------------------------------------------------
# Test: --dry-run flag
# ---------------------------------------------------------------------------


class TestRankingsDryRun:
    """Tests for the --dry-run flag behaviour."""

    def test_dry_run_does_not_call_http(self):
        """Dry-run should scrape but skip the HTTP POST entirely."""
        snapshot = _make_snapshot()
        mock_scraper_instance = _mock_scraper(snapshot)

        with (
            patch(
                "src.cli.main.MLSQoPScraper",
                return_value=mock_scraper_instance,
            ) as MockScraper,
            patch("src.cli.main.httpx") as mock_httpx,
        ):
            result = runner.invoke(app, ["rankings", "--dry-run"])

        assert result.exit_code == 0, result.output
        MockScraper.assert_called_once_with(
            age_group="U14", division="Northeast", headless=True
        )
        mock_scraper_instance.scrape.assert_called_once()
        mock_httpx.post.assert_not_called()

    def test_dry_run_prints_table(self):
        """Dry-run output should include the team names from the snapshot."""
        snapshot = _make_snapshot()

        with patch(
            "src.cli.main.MLSQoPScraper",
            return_value=_mock_scraper(snapshot),
        ):
            result = runner.invoke(app, ["rankings", "--dry-run"])

        assert result.exit_code == 0, result.output
        assert "New York City FC" in result.output

    def test_dry_run_prints_dry_run_message(self):
        """The 'Dry run' notice should appear in the output."""
        snapshot = _make_snapshot()

        with patch(
            "src.cli.main.MLSQoPScraper",
            return_value=_mock_scraper(snapshot),
        ):
            result = runner.invoke(app, ["rankings", "--dry-run"])

        assert result.exit_code == 0, result.output
        assert "Dry run" in result.output


# ---------------------------------------------------------------------------
# Test: missing API token
# ---------------------------------------------------------------------------


class TestRankingsMissingToken:
    """Tests for the case where no API token is provided."""

    def test_missing_token_exits_with_code_1(self, monkeypatch):
        """Command should exit 1 if no token is set and --dry-run is not used."""
        snapshot = _make_snapshot()
        monkeypatch.delenv("MISSING_TABLE_API_TOKEN", raising=False)

        with patch(
            "src.cli.main.MLSQoPScraper",
            return_value=_mock_scraper(snapshot),
        ):
            result = runner.invoke(
                app,
                ["rankings"],
                env={"MISSING_TABLE_API_TOKEN": ""},
            )

        assert result.exit_code == 1

    def test_missing_token_prints_error_message(self, monkeypatch):
        """An informative error should appear when the token is absent."""
        snapshot = _make_snapshot()
        monkeypatch.delenv("MISSING_TABLE_API_TOKEN", raising=False)

        with patch(
            "src.cli.main.MLSQoPScraper",
            return_value=_mock_scraper(snapshot),
        ):
            result = runner.invoke(
                app,
                ["rankings"],
                env={"MISSING_TABLE_API_TOKEN": ""},
            )

        assert "api-token" in result.output.lower() or "token" in result.output.lower()


# ---------------------------------------------------------------------------
# Test: successful POST
# ---------------------------------------------------------------------------


class TestRankingsSuccessfulPost:
    """Tests for the happy-path POST to the MT API."""

    def test_post_called_with_correct_headers(self):
        """httpx.post should be called with the Authorization header."""
        snapshot = _make_snapshot()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        with (
            patch(
                "src.cli.main.MLSQoPScraper",
                return_value=_mock_scraper(snapshot),
            ),
            patch("src.cli.main.httpx") as mock_httpx,
        ):
            mock_httpx.post.return_value = mock_response
            mock_httpx.HTTPStatusError = Exception  # prevent isinstance check issues

            result = runner.invoke(
                app,
                [
                    "rankings",
                    "--api-token",
                    "test-secret",
                    "--api-url",
                    "http://api.example.com",
                ],
            )

        assert result.exit_code == 0, result.output
        mock_httpx.post.assert_called_once()
        call_kwargs = mock_httpx.post.call_args
        assert call_kwargs.kwargs["headers"] == {"Authorization": "Bearer test-secret"}

    def test_post_called_with_correct_url(self):
        """httpx.post should target /api/qop-rankings on the given base URL."""
        snapshot = _make_snapshot()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        with (
            patch(
                "src.cli.main.MLSQoPScraper",
                return_value=_mock_scraper(snapshot),
            ),
            patch("src.cli.main.httpx") as mock_httpx,
        ):
            mock_httpx.post.return_value = mock_response
            mock_httpx.HTTPStatusError = Exception

            result = runner.invoke(
                app,
                [
                    "rankings",
                    "--api-token",
                    "tok",
                    "--api-url",
                    "http://api.example.com",
                ],
            )

        assert result.exit_code == 0, result.output
        url_arg = mock_httpx.post.call_args.args[0]
        assert url_arg == "http://api.example.com/api/qop-rankings"

    def test_post_body_is_snapshot_json(self):
        """The POST body should be the full snapshot serialised as JSON."""
        snapshot = _make_snapshot()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        with (
            patch(
                "src.cli.main.MLSQoPScraper",
                return_value=_mock_scraper(snapshot),
            ),
            patch("src.cli.main.httpx") as mock_httpx,
        ):
            mock_httpx.post.return_value = mock_response
            mock_httpx.HTTPStatusError = Exception

            result = runner.invoke(
                app,
                [
                    "rankings",
                    "--api-token",
                    "tok",
                    "--api-url",
                    "http://api.example.com",
                ],
            )

        assert result.exit_code == 0, result.output
        posted_json = mock_httpx.post.call_args.kwargs["json"]
        assert posted_json["age_group"] == "U14"
        assert posted_json["division"] == "Northeast"
        assert len(posted_json["rankings"]) == 2

    def test_success_message_printed(self):
        """A success message including the ranking count should be printed."""
        snapshot = _make_snapshot()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        with (
            patch(
                "src.cli.main.MLSQoPScraper",
                return_value=_mock_scraper(snapshot),
            ),
            patch("src.cli.main.httpx") as mock_httpx,
        ):
            mock_httpx.post.return_value = mock_response
            mock_httpx.HTTPStatusError = Exception

            result = runner.invoke(
                app,
                [
                    "rankings",
                    "--api-token",
                    "tok",
                    "--api-url",
                    "http://api.example.com",
                ],
            )

        assert result.exit_code == 0, result.output
        assert "2" in result.output  # ranking count
        assert "2026-04-13" in result.output  # week_of date


# ---------------------------------------------------------------------------
# Test: HTTP error handling
# ---------------------------------------------------------------------------


class TestRankingsUnchangedResponse:
    """The rankings command should surface MT's `status: unchanged` reply
    distinctly from a fresh insert."""

    def test_unchanged_status_printed_when_mt_reports_no_change(self):
        snapshot = _make_snapshot()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.content = b'{"status":"unchanged","detected_at":"2026-04-10"}'
        mock_response.json.return_value = {
            "status": "unchanged",
            "detected_at": "2026-04-10",
        }

        with (
            patch(
                "src.cli.main.MLSQoPScraper",
                return_value=_mock_scraper(snapshot),
            ),
            patch("src.cli.main.httpx") as mock_httpx,
        ):
            mock_httpx.post.return_value = mock_response
            mock_httpx.HTTPStatusError = Exception

            result = runner.invoke(
                app,
                [
                    "rankings",
                    "--api-token",
                    "tok",
                    "--api-url",
                    "http://api.example.com",
                ],
            )

        assert result.exit_code == 0, result.output
        # Rich injects ANSI colour codes that break substring match on dashes/digits.
        import re as _re

        plain = _re.sub(r"\x1b\[[0-9;]*m", "", result.output)
        assert "no change" in plain.lower() or "unchanged" in plain.lower()
        assert "2026-04-10" in plain


class TestRankingsTeamNameNormalization:
    """Tests that the rankings command applies the same team-name mapping
    used by match scraping before POSTing to MT."""

    def _snapshot_with_ifa(self) -> QoPSnapshot:
        return QoPSnapshot(
            detected_at=date(2026, 4, 13),
            division="Northeast",
            age_group="U14",
            scraped_at=datetime(2026, 4, 16, 10, 0, 0, tzinfo=timezone.utc),
            rankings=[
                QoPRanking(
                    rank=13,
                    team_name="Intercontinental Football Academy of New England",
                    matches_played=16,
                    att_score=74.7,
                    def_score=74.4,
                    qop_score=74.6,
                ),
            ],
        )

    def test_posted_team_name_is_normalized(self):
        """POST body must contain the short MT-friendly name, not the raw MLS Next name."""
        snapshot = self._snapshot_with_ifa()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        with (
            patch(
                "src.cli.main.MLSQoPScraper",
                return_value=_mock_scraper(snapshot),
            ),
            patch("src.cli.main.httpx") as mock_httpx,
        ):
            mock_httpx.post.return_value = mock_response
            mock_httpx.HTTPStatusError = Exception

            result = runner.invoke(
                app,
                [
                    "rankings",
                    "--api-token",
                    "tok",
                    "--api-url",
                    "http://api.example.com",
                ],
            )

        assert result.exit_code == 0, result.output
        posted_json = mock_httpx.post.call_args.kwargs["json"]
        assert posted_json["rankings"][0]["team_name"] == "IFA"

    def test_dry_run_output_shows_normalized_name(self):
        """Dry-run table should also display the normalized name."""
        snapshot = self._snapshot_with_ifa()

        with patch(
            "src.cli.main.MLSQoPScraper",
            return_value=_mock_scraper(snapshot),
        ):
            result = runner.invoke(app, ["rankings", "--dry-run"])

        assert result.exit_code == 0, result.output
        assert "IFA" in result.output


class TestRankingsHttpError:
    """Tests for HTTP error responses from the API."""

    def test_http_error_exits_code_1(self):
        """An HTTP error response should cause exit code 1."""
        import httpx as real_httpx

        snapshot = _make_snapshot()

        # Build a real HTTPStatusError so isinstance checks work
        mock_request = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        http_err = real_httpx.HTTPStatusError(
            "500", request=mock_request, response=mock_resp
        )

        with (
            patch(
                "src.cli.main.MLSQoPScraper",
                return_value=_mock_scraper(snapshot),
            ),
            patch("src.cli.main.httpx.post", side_effect=http_err),
        ):
            result = runner.invoke(
                app,
                [
                    "rankings",
                    "--api-token",
                    "tok",
                    "--api-url",
                    "http://api.example.com",
                ],
            )

        assert result.exit_code == 1
