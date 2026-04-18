"""Unit tests for MLSQoPScraper (httpx + BeautifulSoup implementation)."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.scraper.qop_scraper import (
    AGE_GROUP_IDS,
    MLSQoPScraper,
    QoPScraperError,
    _normalize_division_heading,
    strip_qualification_text,
)

# ---------------------------------------------------------------------------
# strip_qualification_text
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestStripQualificationText:
    def test_plain_name_unchanged(self):
        assert strip_qualification_text("New York City FC") == "New York City FC"

    def test_championship_qualification_removed(self):
        assert (
            strip_qualification_text("New York City FCChampionship Qualification")
            == "New York City FC"
        )

    def test_premier_qualification_removed(self):
        assert (
            strip_qualification_text("FC Dallas Premier Qualification") == "FC Dallas"
        )

    def test_bare_qualification_removed(self):
        assert strip_qualification_text("LA Galaxy Qualification") == "LA Galaxy"

    def test_case_insensitive_removal(self):
        assert (
            strip_qualification_text("Chicago Fire FC championship qualification")
            == "Chicago Fire FC"
        )

    def test_leading_trailing_whitespace_stripped(self):
        assert strip_qualification_text("  Real Salt Lake  ") == "Real Salt Lake"

    def test_empty_string(self):
        assert strip_qualification_text("") == ""

    def test_multiple_spaces_collapsed(self):
        result = strip_qualification_text("Portland  Timbers  Qualification")
        assert "  " not in result
        assert result == "Portland Timbers"


# ---------------------------------------------------------------------------
# _normalize_division_heading
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestNormalizeDivisionHeading:
    def test_strips_age_prefix(self):
        assert _normalize_division_heading("U15 Northeast Division") == "northeast"

    def test_strips_age_prefix_lowercase(self):
        assert _normalize_division_heading("u14 Northeast Division") == "northeast"

    def test_no_age_prefix(self):
        assert _normalize_division_heading("Northeast Division") == "northeast"

    def test_preserves_pathway_suffix(self):
        assert (
            _normalize_division_heading("U16 Northeast (Pro Player Pathway) Division")
            == "northeast (pro player pathway)"
        )

    def test_whitespace_stripped(self):
        assert (
            _normalize_division_heading("  Mid-Atlantic Division  ") == "mid-atlantic"
        )


# ---------------------------------------------------------------------------
# Init validation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMLSQoPScraperInit:
    def test_accepts_known_age_group(self):
        scraper = MLSQoPScraper(age_group="U14", division="Northeast")
        assert scraper.age_id == AGE_GROUP_IDS["U14"]
        assert scraper.division == "Northeast"

    def test_rejects_unknown_age_group(self):
        with pytest.raises(QoPScraperError, match="Unknown age group"):
            MLSQoPScraper(age_group="U99", division="Northeast")

    def test_division_target_is_normalized(self):
        scraper = MLSQoPScraper(age_group="U14", division="Northeast")
        assert scraper._division_target == "northeast"

    def test_all_age_groups_have_mapping(self):
        for age in ["U13", "U14", "U15", "U16", "U17", "U19"]:
            scraper = MLSQoPScraper(age_group=age, division="Northeast")
            assert scraper.age_id == AGE_GROUP_IDS[age]

    def test_accepts_headless_kwarg_for_backwards_compat(self):
        # CLI passes headless=True/False; scraper should accept without error.
        MLSQoPScraper(age_group="U14", division="Northeast", headless=False)


# ---------------------------------------------------------------------------
# Parser (fixture-based HTML)
# ---------------------------------------------------------------------------


def _qop_row_html(
    rank: int, team: str, mp: int, att: float, defn: float, qop: float
) -> str:
    return f"""
    <div class="form_row row main_row" js-group="41" row="division{rank}">
      <div class="col-xs-9 col-sm-6">
        <div class="row subrow pad-right">
          <div class="col-xs-1 col-sm-2 container-rank pad-0 text-center">{rank}</div>
          <div class="col-xs-9 col-sm-8">
            <div class="container-team-info">
              <p data-title="{team}">{team}</p>
            </div>
          </div>
        </div>
      </div>
      <div class="col-xs-3 col-sm-6">
        <div class="row subrow pad-left">
          <div class="col-sm-3 pad-0 gap-right-mobile-lg hidden-xs">{mp}</div>
          <div class="col-sm-3 pad-0 gap-right-mobile-lg hidden-xs">{att}</div>
          <div class="col-sm-3 pad-0 gap-right-mobile-sm hidden-xs">{defn}</div>
          <div class="col-sm-3 pad-0 gap-right-mobile-sm hidden-xs">{qop}</div>
        </div>
      </div>
    </div>
    """


def _traditional_row_html(rank: int, team: str) -> str:
    """A non-QoP standings row (9 col-sm-1 cells). Should be skipped."""
    cells = "".join(
        f'<div class="col-sm-1 pad-0 hidden-xs">{i}</div>' for i in range(9)
    )
    return f"""
    <div class="form_row row main_row" js-group="41" row="division{rank}">
      <div class="col-xs-9 col-sm-6">
        <div class="row subrow pad-right">
          <div class="col-xs-1 col-sm-2 container-rank pad-0 text-center">{rank}</div>
          <div class="container-team-info"><p data-title="{team}">{team}</p></div>
        </div>
      </div>
      <div class="col-xs-3 col-sm-6">
        <div class="row subrow pad-left">{cells}</div>
      </div>
    </div>
    """


def _heading_html(title: str) -> str:
    return f'<p data-title="{title}">{title}</p>'


@pytest.mark.unit
class TestParseRankings:
    def test_extracts_target_division_rows(self):
        html = (
            _heading_html("Mid-Atlantic Division")
            + _qop_row_html(1, "Other Team", 10, 70.0, 70.0, 70.0)
            + _heading_html("Northeast Division")
            + _qop_row_html(1, "New York City FC", 16, 89.6, 83.1, 87.6)
            + _qop_row_html(2, "Red Bulls", 15, 87.3, 78.8, 84.8)
        )
        scraper = MLSQoPScraper(age_group="U14", division="Northeast")
        rankings = scraper._parse_rankings(html)
        assert len(rankings) == 2
        assert rankings[0].rank == 1
        assert rankings[0].team_name == "New York City FC"
        assert rankings[0].qop_score == 87.6
        assert rankings[1].team_name == "Red Bulls"

    def test_rankings_sorted_by_rank(self):
        html = (
            _heading_html("Northeast Division")
            + _qop_row_html(3, "C", 10, 70.0, 70.0, 70.0)
            + _qop_row_html(1, "A", 10, 90.0, 90.0, 90.0)
            + _qop_row_html(2, "B", 10, 80.0, 80.0, 80.0)
        )
        scraper = MLSQoPScraper(age_group="U14", division="Northeast")
        rankings = scraper._parse_rankings(html)
        assert [r.rank for r in rankings] == [1, 2, 3]
        assert [r.team_name for r in rankings] == ["A", "B", "C"]

    def test_matches_with_age_prefixed_heading(self):
        html = _heading_html("U15 Northeast Division") + _qop_row_html(
            1, "Team A", 10, 80.0, 80.0, 80.0
        )
        scraper = MLSQoPScraper(age_group="U15", division="Northeast")
        rankings = scraper._parse_rankings(html)
        assert len(rankings) == 1
        assert rankings[0].team_name == "Team A"

    def test_skips_pro_player_pathway_when_geographic_requested(self):
        html = (
            _heading_html("U16 Northeast (Pro Player Pathway) Division")
            + _qop_row_html(1, "Pathway Team", 10, 80.0, 80.0, 80.0)
            + _heading_html("U16 Northeast Division")
            + _qop_row_html(1, "Geographic Team", 10, 85.0, 85.0, 85.0)
        )
        scraper = MLSQoPScraper(age_group="U16", division="Northeast")
        rankings = scraper._parse_rankings(html)
        assert len(rankings) == 1
        assert rankings[0].team_name == "Geographic Team"

    def test_skips_traditional_standings_rows(self):
        html = (
            _heading_html("U15 Northeast Division")
            + _traditional_row_html(1, "Team A")
            + _traditional_row_html(2, "Team B")
        )
        scraper = MLSQoPScraper(age_group="U15", division="Northeast")
        rankings = scraper._parse_rankings(html)
        assert rankings == []

    def test_raises_when_target_division_missing(self):
        html = _heading_html("Mid-Atlantic Division") + _qop_row_html(
            1, "X", 10, 70.0, 70.0, 70.0
        )
        scraper = MLSQoPScraper(age_group="U14", division="Northeast")
        with pytest.raises(QoPScraperError, match="not found"):
            scraper._parse_rankings(html)

    def test_qualification_text_stripped_from_team_name(self):
        html = (
            _heading_html("Northeast Division")
            + """
        <div class="form_row row main_row" js-group="41" row="division1">
          <div class="col-xs-9 col-sm-6">
            <div class="row subrow pad-right">
              <div class="col-xs-1 col-sm-2 container-rank pad-0 text-center">1</div>
              <div class="container-team-info">
                <p data-title="Philadelphia Union">
                  Philadelphia Union Championship Qualification
                </p>
              </div>
            </div>
          </div>
          <div class="col-xs-3 col-sm-6">
            <div class="row subrow pad-left">
              <div class="col-sm-3 pad-0 hidden-xs">16</div>
              <div class="col-sm-3 pad-0 hidden-xs">85.6</div>
              <div class="col-sm-3 pad-0 hidden-xs">82.1</div>
              <div class="col-sm-3 pad-0 hidden-xs">84.5</div>
            </div>
          </div>
        </div>
        """
        )
        scraper = MLSQoPScraper(age_group="U14", division="Northeast")
        rankings = scraper._parse_rankings(html)
        assert rankings[0].team_name == "Philadelphia Union"


# ---------------------------------------------------------------------------
# scrape() — end-to-end with mocked HTTP
# ---------------------------------------------------------------------------


def _make_successful_html() -> str:
    return (
        _heading_html("Northeast Division")
        + _qop_row_html(1, "New York City FC", 16, 89.6, 83.1, 87.6)
        + _qop_row_html(2, "Red Bulls", 15, 87.3, 78.8, 84.8)
    )


@pytest.mark.unit
@pytest.mark.asyncio
class TestScrape:
    async def test_scrape_returns_snapshot_with_rankings(self):
        scraper = MLSQoPScraper(age_group="U14", division="Northeast")

        with patch.object(scraper, "_fetch_html", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = _make_successful_html()
            snapshot = await scraper.scrape()

        assert snapshot.age_group == "U14"
        assert snapshot.division == "Northeast"
        assert len(snapshot.rankings) == 2
        assert snapshot.rankings[0].team_name == "New York City FC"

    async def test_scrape_detected_at_is_today(self):
        """detected_at is set to date.today() — it represents when the scraper
        observed the rankings, not a wall-clock week boundary."""
        scraper = MLSQoPScraper(age_group="U14", division="Northeast")
        with patch.object(scraper, "_fetch_html", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = _make_successful_html()
            snapshot = await scraper.scrape()

        assert snapshot.detected_at == date.today()

    async def test_scrape_raises_when_rankings_empty(self):
        scraper = MLSQoPScraper(age_group="U14", division="Northeast")
        html = _heading_html("Northeast Division")  # heading but no rows
        with patch.object(scraper, "_fetch_html", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = html
            with pytest.raises(QoPScraperError, match="No QoP rankings found"):
                await scraper.scrape()

    async def test_scrape_reraises_division_not_found(self):
        scraper = MLSQoPScraper(age_group="U14", division="Northeast")
        html = _heading_html("Mid-Atlantic Division") + _qop_row_html(
            1, "X", 10, 70.0, 70.0, 70.0
        )
        with patch.object(scraper, "_fetch_html", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = html
            with pytest.raises(QoPScraperError, match="not found"):
                await scraper.scrape()


# ---------------------------------------------------------------------------
# _fetch_html — retry + error paths
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
class TestFetchHtml:
    async def test_retries_on_http_error_then_succeeds(self):
        scraper = MLSQoPScraper(age_group="U14", division="Northeast")

        call_count = 0

        async def fake_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise httpx.ConnectError("boom")
            request = httpx.Request("GET", MLSQoPScraper.ENDPOINT_URL)
            return httpx.Response(200, text="<html>ok</html>", request=request)

        with (
            patch("httpx.AsyncClient.get", side_effect=fake_get),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            html = await scraper._fetch_html()

        assert "ok" in html
        assert call_count == 2

    async def test_raises_after_max_retries(self):
        scraper = MLSQoPScraper(age_group="U14", division="Northeast")

        async def always_fail(*args, **kwargs):
            raise httpx.ConnectError("boom")

        with (
            patch("httpx.AsyncClient.get", side_effect=always_fail),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            with pytest.raises(QoPScraperError, match="attempts"):
                await scraper._fetch_html()
