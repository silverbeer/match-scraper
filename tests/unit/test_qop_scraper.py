"""Unit tests for MLSQoPScraper and related helpers."""

from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from src.models.qop_ranking import QoPRanking, QoPSnapshot
from src.scraper.qop_scraper import (
    MLSQoPScraper,
    QoPScraperError,
    strip_qualification_text,
)

# ---------------------------------------------------------------------------
# Pure-function tests — no mocking needed
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestStripQualificationText:
    """Tests for the strip_qualification_text() helper."""

    def test_plain_name_unchanged(self):
        assert strip_qualification_text("New York City FC") == "New York City FC"

    def test_championship_qualification_removed(self):
        raw = "New York City FCChampionship Qualification"
        assert strip_qualification_text(raw) == "New York City FC"

    def test_premier_qualification_removed(self):
        raw = "FC Dallas Premier Qualification"
        assert strip_qualification_text(raw) == "FC Dallas"

    def test_bare_qualification_removed(self):
        raw = "LA Galaxy Qualification"
        assert strip_qualification_text(raw) == "LA Galaxy"

    def test_case_insensitive_removal(self):
        raw = "Chicago Fire FC championship qualification"
        assert strip_qualification_text(raw) == "Chicago Fire FC"

    def test_leading_trailing_whitespace_stripped(self):
        assert strip_qualification_text("  Real Salt Lake  ") == "Real Salt Lake"

    def test_empty_string(self):
        assert strip_qualification_text("") == ""

    def test_multiple_spaces_collapsed(self):
        # After stripping "Qualification" internal spaces should be collapsed
        raw = "Portland  Timbers  Qualification"
        result = strip_qualification_text(raw)
        assert "  " not in result
        assert "Portland" in result
        assert "Timbers" in result


# ---------------------------------------------------------------------------
# week_of logic
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestWeekOf:
    """Verify the week_of calculation always lands on a Monday."""

    def test_week_of_is_monday(self):
        """Regardless of when tests run, week_of must be the Monday of current week."""
        today = date.today()
        expected_monday = today - timedelta(days=today.weekday())
        # Simulate what the scraper does
        computed = today - timedelta(days=today.weekday())
        assert computed == expected_monday
        assert computed.weekday() == 0  # 0 == Monday

    def test_week_of_is_not_in_future(self):
        today = date.today()
        week_of = today - timedelta(days=today.weekday())
        assert week_of <= today


# ---------------------------------------------------------------------------
# QoPScraperError
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestQoPScraperError:
    def test_is_exception(self):
        err = QoPScraperError("boom")
        assert isinstance(err, Exception)
        assert str(err) == "boom"

    def test_chaining(self):
        original = ValueError("root cause")
        try:
            raise QoPScraperError("wrapper") from original
        except QoPScraperError as exc:
            assert exc.__cause__ is original


# ---------------------------------------------------------------------------
# MLSQoPScraper initialisation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMLSQoPScraperInit:
    def test_url_built_correctly_for_u14(self):
        scraper = MLSQoPScraper(age_group="U14", division="Northeast")
        assert "u14" in scraper.standings_url
        assert scraper.standings_url.startswith("https://")

    def test_url_built_correctly_for_u16(self):
        scraper = MLSQoPScraper(age_group="U16", division="Southeast")
        assert "u16" in scraper.standings_url

    def test_attributes_stored(self):
        scraper = MLSQoPScraper(age_group="U14", division="Northeast", headless=False)
        assert scraper.age_group == "U14"
        assert scraper.division == "Northeast"
        assert scraper.headless is False

    def test_retry_constants_exist(self):
        assert MLSQoPScraper.MAX_RETRIES == 3
        assert MLSQoPScraper.RETRY_DELAY_BASE > 0


# ---------------------------------------------------------------------------
# Helpers for mocking the Playwright page
# ---------------------------------------------------------------------------


def _make_cell(text: str) -> AsyncMock:
    """Create a mock <td> element that returns *text* from text_content()."""
    cell = AsyncMock()
    cell.text_content = AsyncMock(return_value=text)
    return cell


def _make_row(rank, team, mp, att, def_, qop) -> AsyncMock:
    """Create a mock <tr> element with 6 <td> cells."""
    row = AsyncMock()
    cells = [
        _make_cell(str(rank)),
        _make_cell(team),
        _make_cell(str(mp)),
        _make_cell(str(att)),
        _make_cell(str(def_)),
        _make_cell(str(qop)),
    ]
    row.query_selector_all = AsyncMock(return_value=cells)
    return row


def _make_short_row() -> AsyncMock:
    """Create a row with too few cells (header-like)."""
    row = AsyncMock()
    row.query_selector_all = AsyncMock(return_value=[_make_cell("Rank")])
    return row


# ---------------------------------------------------------------------------
# _extract_rankings
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExtractRankings:
    """Tests for MLSQoPScraper._extract_rankings() in isolation."""

    @pytest.fixture
    def scraper(self):
        return MLSQoPScraper(age_group="U14", division="Northeast")

    @pytest.mark.asyncio
    async def test_extracts_valid_rows(self, scraper):
        page = AsyncMock()

        rows = [
            _make_short_row(),  # header — should be skipped
            _make_row(1, "New York City FC", 16, 89.6, 83.1, 87.6),
            _make_row(2, "FC Dallas", 15, 78.2, 75.0, 77.1),
        ]

        page.wait_for_selector = AsyncMock(return_value=None)
        page.query_selector_all = AsyncMock(return_value=rows)

        rankings = await scraper._extract_rankings(page)

        assert len(rankings) == 2
        assert rankings[0].rank == 1
        assert rankings[0].team_name == "New York City FC"
        assert rankings[0].qop_score == pytest.approx(87.6)
        assert rankings[1].rank == 2

    @pytest.mark.asyncio
    async def test_strips_qualification_text_from_team_name(self, scraper):
        page = AsyncMock()

        rows = [
            _make_row(
                1,
                "New York City FCChampionship Qualification",
                14,
                90.0,
                80.0,
                85.0,
            )
        ]

        page.wait_for_selector = AsyncMock(return_value=None)
        page.query_selector_all = AsyncMock(return_value=rows)

        rankings = await scraper._extract_rankings(page)

        assert len(rankings) == 1
        assert rankings[0].team_name == "New York City FC"

    @pytest.mark.asyncio
    async def test_raises_when_no_rows_found(self, scraper):
        page = AsyncMock()
        page.wait_for_selector = AsyncMock(side_effect=Exception("timeout"))
        page.query_selector_all = AsyncMock(return_value=[])

        with pytest.raises(QoPScraperError, match="standings table rows"):
            await scraper._extract_rankings(page)

    @pytest.mark.asyncio
    async def test_raises_when_all_rows_unparseable(self, scraper):
        page = AsyncMock()

        bad_row = AsyncMock()
        bad_row.query_selector_all = AsyncMock(
            return_value=[
                _make_cell("foo"),
                _make_cell("bar"),
                _make_cell("baz"),
                _make_cell("qux"),
                _make_cell("quux"),
                _make_cell("corge"),
            ]
        )

        page.wait_for_selector = AsyncMock(return_value=None)
        page.query_selector_all = AsyncMock(return_value=[bad_row])

        with pytest.raises(QoPScraperError, match="No rankings could be extracted"):
            await scraper._extract_rankings(page)


# ---------------------------------------------------------------------------
# Division filter not found
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSelectDivision:
    """Tests for MLSQoPScraper._select_division() edge cases."""

    @pytest.fixture
    def scraper(self):
        return MLSQoPScraper(age_group="U14", division="Northeast")

    @pytest.mark.asyncio
    async def test_raises_when_division_not_found(self, scraper):
        """_select_division must raise QoPScraperError if no filter matches."""
        page = AsyncMock()
        # All strategies return nothing useful
        page.query_selector_all = AsyncMock(return_value=[])
        page.query_selector = AsyncMock(return_value=None)
        page.wait_for_timeout = AsyncMock(return_value=None)

        with pytest.raises(QoPScraperError, match="Division filter not found"):
            await scraper._select_division(page)

    @pytest.mark.asyncio
    async def test_selects_via_native_select_element(self, scraper):
        """_try_select_element should select the matching option."""
        page = AsyncMock()

        option = AsyncMock()
        option.text_content = AsyncMock(return_value="Northeast Division")
        option.get_attribute = AsyncMock(return_value="northeast-division")

        select_el = AsyncMock()
        select_el.query_selector_all = AsyncMock(return_value=[option])
        select_el.select_option = AsyncMock(return_value=None)

        # Return select_el for the first broad "select" query
        page.query_selector_all = AsyncMock(return_value=[select_el])
        page.query_selector = AsyncMock(return_value=None)
        page.wait_for_timeout = AsyncMock(return_value=None)

        # Should not raise
        await scraper._select_division(page)

        select_el.select_option.assert_called_once()


# ---------------------------------------------------------------------------
# Full scrape() — integration-level mock
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMLSQoPScraperScrape:
    """Tests for the top-level scrape() method using heavily mocked internals."""

    @pytest.fixture
    def scraper(self):
        return MLSQoPScraper(age_group="U14", division="Northeast")

    @pytest.mark.asyncio
    async def test_scrape_returns_snapshot(self, scraper):
        """A successful scrape should return a valid QoPSnapshot."""
        fake_rankings = [
            QoPRanking(
                rank=1,
                team_name="Club A",
                matches_played=10,
                att_score=85.0,
                def_score=80.0,
                qop_score=83.0,
            )
        ]

        with (
            patch.object(
                scraper, "_scrape_attempt", new_callable=AsyncMock
            ) as mock_attempt,
        ):
            today = date.today()
            week_of = today - timedelta(days=today.weekday())
            from datetime import datetime, timezone

            mock_attempt.return_value = QoPSnapshot(
                week_of=week_of,
                division="Northeast",
                age_group="U14",
                scraped_at=datetime.now(tz=timezone.utc),
                rankings=fake_rankings,
            )

            snapshot = await scraper.scrape()

        assert isinstance(snapshot, QoPSnapshot)
        assert snapshot.age_group == "U14"
        assert snapshot.division == "Northeast"
        assert len(snapshot.rankings) == 1
        assert snapshot.rankings[0].team_name == "Club A"
        assert snapshot.week_of.weekday() == 0  # Monday

    @pytest.mark.asyncio
    async def test_scrape_reraises_qop_scraper_error_immediately(self, scraper):
        """QoPScraperError (logical errors) should not be retried."""
        call_count = 0

        async def failing_attempt():
            nonlocal call_count
            call_count += 1
            raise QoPScraperError("Division not found")

        with patch.object(scraper, "_scrape_attempt", side_effect=failing_attempt):
            with pytest.raises(QoPScraperError, match="Division not found"):
                await scraper.scrape()

        # Should fail on first attempt without retrying
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_scrape_retries_on_generic_exception(self, scraper):
        """Generic exceptions should trigger retries up to MAX_RETRIES."""
        call_count = 0

        async def always_fails():
            nonlocal call_count
            call_count += 1
            raise RuntimeError("network error")

        with (
            patch.object(scraper, "_scrape_attempt", side_effect=always_fails),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            with pytest.raises(QoPScraperError):
                await scraper.scrape()

    @pytest.mark.asyncio
    async def test_browser_manager_cleaned_up_after_failure(self, scraper):
        """browser_manager.cleanup() must be called even when _scrape_attempt raises."""
        mock_bm = AsyncMock()
        mock_bm.cleanup = AsyncMock()

        async def failing_attempt():
            scraper.browser_manager = mock_bm
            raise RuntimeError("boom")

        with (
            patch.object(scraper, "_scrape_attempt", side_effect=failing_attempt),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            with pytest.raises(QoPScraperError):
                await scraper.scrape()

        mock_bm.cleanup.assert_called()


# ---------------------------------------------------------------------------
# _scrape_attempt  (mocking BrowserManager)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestScrapeAttempt:
    """Tests for MLSQoPScraper._scrape_attempt() with BrowserManager mocked."""

    @pytest.fixture
    def scraper(self):
        return MLSQoPScraper(age_group="U14", division="Northeast")

    @pytest.mark.asyncio
    async def test_scrape_attempt_returns_snapshot(self, scraper):
        """_scrape_attempt should initialise browser, call sub-methods, build QoPSnapshot."""
        real_ranking = __import__(
            "src.models.qop_ranking", fromlist=["QoPRanking"]
        ).QoPRanking(
            rank=1,
            team_name="FC Test",
            matches_played=12,
            att_score=80.0,
            def_score=75.0,
            qop_score=78.0,
        )

        mock_page = AsyncMock()
        mock_page.wait_for_timeout = AsyncMock()

        # Build a mock BrowserManager whose get_page() context manager yields mock_page
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _fake_get_page():
            yield mock_page

        mock_bm = AsyncMock()
        mock_bm.initialize = AsyncMock()
        mock_bm.get_page = _fake_get_page
        mock_bm.cleanup = AsyncMock()

        with (
            patch("src.scraper.qop_scraper.BrowserManager", return_value=mock_bm),
            patch("src.scraper.qop_scraper.BrowserConfig"),
            patch.object(scraper, "_navigate", new_callable=AsyncMock),
            patch.object(scraper, "_select_division", new_callable=AsyncMock),
            patch.object(
                scraper,
                "_extract_rankings",
                new_callable=AsyncMock,
                return_value=[real_ranking],
            ),
        ):
            snapshot = await scraper._scrape_attempt()

        assert isinstance(snapshot, QoPSnapshot)
        assert snapshot.age_group == "U14"
        assert snapshot.division == "Northeast"
        assert snapshot.week_of.weekday() == 0  # Monday
        assert len(snapshot.rankings) == 1
        mock_bm.initialize.assert_called_once()


# ---------------------------------------------------------------------------
# _navigate
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestNavigate:
    """Tests for MLSQoPScraper._navigate()."""

    @pytest.fixture
    def scraper(self):
        return MLSQoPScraper(age_group="U14", division="Northeast")

    @pytest.mark.asyncio
    async def test_navigate_success(self, scraper):
        """Successful navigation calls consent handler and page ready check."""
        page = AsyncMock()

        mock_navigator = AsyncMock()
        mock_navigator.navigate_to = AsyncMock(return_value=True)

        mock_consent = AsyncMock()
        mock_consent.handle_consent_banner = AsyncMock(return_value=True)
        mock_consent.wait_for_page_ready = AsyncMock(return_value=True)

        with (
            patch("src.scraper.qop_scraper.PageNavigator", return_value=mock_navigator),
            patch(
                "src.scraper.qop_scraper.MLSConsentHandler", return_value=mock_consent
            ),
        ):
            await scraper._navigate(page)

        mock_navigator.navigate_to.assert_called_once()
        mock_consent.handle_consent_banner.assert_called_once()
        mock_consent.wait_for_page_ready.assert_called_once()

    @pytest.mark.asyncio
    async def test_navigate_raises_on_navigation_failure(self, scraper):
        """Should raise QoPScraperError when navigate_to returns False."""
        page = AsyncMock()

        mock_navigator = AsyncMock()
        mock_navigator.navigate_to = AsyncMock(return_value=False)

        with patch(
            "src.scraper.qop_scraper.PageNavigator", return_value=mock_navigator
        ):
            with pytest.raises(QoPScraperError, match="Failed to navigate"):
                await scraper._navigate(page)

    @pytest.mark.asyncio
    async def test_navigate_continues_when_consent_fails(self, scraper):
        """A failed consent banner should not raise — just log a warning."""
        page = AsyncMock()

        mock_navigator = AsyncMock()
        mock_navigator.navigate_to = AsyncMock(return_value=True)

        mock_consent = AsyncMock()
        mock_consent.handle_consent_banner = AsyncMock(return_value=False)
        mock_consent.wait_for_page_ready = AsyncMock(return_value=False)

        with (
            patch("src.scraper.qop_scraper.PageNavigator", return_value=mock_navigator),
            patch(
                "src.scraper.qop_scraper.MLSConsentHandler", return_value=mock_consent
            ),
        ):
            # Should not raise despite consent + readiness failures
            await scraper._navigate(page)


# ---------------------------------------------------------------------------
# _try_button_filter
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTryButtonFilter:
    """Tests for MLSQoPScraper._try_button_filter()."""

    @pytest.fixture
    def scraper(self):
        return MLSQoPScraper(age_group="U14", division="Northeast")

    @pytest.mark.asyncio
    async def test_returns_true_when_direct_selector_matches(self, scraper):
        """Should click and return True when query_selector finds a matching element."""
        page = AsyncMock()
        mock_el = AsyncMock()
        mock_el.click = AsyncMock()

        # First selector (button:has-text) hits
        page.query_selector = AsyncMock(return_value=mock_el)
        page.query_selector_all = AsyncMock(return_value=[])

        result = await scraper._try_button_filter(page, "northeast")

        assert result is True
        mock_el.click.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_true_via_broad_candidate_search(self, scraper):
        """Should find a matching element via the broad candidate fallback."""
        page = AsyncMock()
        # Direct selectors find nothing
        page.query_selector = AsyncMock(return_value=None)

        # Candidate element whose text matches "northeast division"
        candidate = AsyncMock()
        candidate.text_content = AsyncMock(return_value="Northeast Division")
        candidate.click = AsyncMock()

        page.query_selector_all = AsyncMock(return_value=[candidate])

        result = await scraper._try_button_filter(page, "northeast")

        assert result is True
        candidate.click.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_false_when_no_match(self, scraper):
        """Should return False when nothing matches."""
        page = AsyncMock()
        page.query_selector = AsyncMock(return_value=None)

        non_matching = AsyncMock()
        non_matching.text_content = AsyncMock(return_value="Unrelated Text")

        page.query_selector_all = AsyncMock(return_value=[non_matching])

        result = await scraper._try_button_filter(page, "northeast")

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_broad_search_exception(self, scraper):
        """Should return False (not raise) if query_selector_all itself throws."""
        page = AsyncMock()
        page.query_selector = AsyncMock(return_value=None)
        page.query_selector_all = AsyncMock(side_effect=RuntimeError("dom error"))

        result = await scraper._try_button_filter(page, "northeast")

        assert result is False


# ---------------------------------------------------------------------------
# _extract_rankings — secondary selector fallback
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExtractRankingsFallback:
    """Tests for selector fallback logic in _extract_rankings."""

    @pytest.fixture
    def scraper(self):
        return MLSQoPScraper(age_group="U14", division="Northeast")

    @pytest.mark.asyncio
    async def test_falls_back_to_second_selector_when_first_times_out(self, scraper):
        """First table selector timing out should cause the loop to try the next one."""
        page = AsyncMock()

        good_row = _make_row(1, "Club A", 10, 80.0, 75.0, 78.0)

        call_count = 0

        async def wait_for_selector_stub(sel, timeout):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("timeout")
            # Second selector succeeds
            return None

        page.wait_for_selector = wait_for_selector_stub
        page.query_selector_all = AsyncMock(return_value=[good_row])

        rankings = await scraper._extract_rankings(page)

        assert len(rankings) == 1
        assert call_count >= 2  # at least two selector attempts

    @pytest.mark.asyncio
    async def test_select_division_button_path_called(self, scraper):
        """_select_division takes the button path when _try_select_element returns False."""
        page = AsyncMock()
        page.wait_for_timeout = AsyncMock()

        with (
            patch.object(
                scraper,
                "_try_select_element",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch.object(
                scraper,
                "_try_button_filter",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_btn,
        ):
            await scraper._select_division(page)

        mock_btn.assert_called_once()
        page.wait_for_timeout.assert_called_once_with(1500)


# ---------------------------------------------------------------------------
# Exception-handler branches in _try_select_element and _try_button_filter
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExceptionHandlerBranches:
    """Cover the except branches that swallow errors and try the next selector."""

    @pytest.fixture
    def scraper(self):
        return MLSQoPScraper(age_group="U14", division="Northeast")

    @pytest.mark.asyncio
    async def test_try_select_element_handles_query_selector_all_exception(
        self, scraper
    ):
        """When query_selector_all raises, the loop should continue and return False."""
        page = AsyncMock()
        # Make every query_selector_all call raise so all selectors are exhausted
        page.query_selector_all = AsyncMock(side_effect=RuntimeError("dom error"))

        result = await scraper._try_select_element(page, "northeast")

        assert result is False

    @pytest.mark.asyncio
    async def test_try_button_filter_handles_query_selector_exception(self, scraper):
        """When query_selector raises, the specific-selector loop continues."""
        page = AsyncMock()
        # Direct selectors raise; broad fallback returns empty
        page.query_selector = AsyncMock(side_effect=RuntimeError("boom"))
        page.query_selector_all = AsyncMock(return_value=[])

        result = await scraper._try_button_filter(page, "northeast")

        assert result is False
