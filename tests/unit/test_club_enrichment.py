"""Unit tests for club enrichment module."""

import json
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.models.discovery import DiscoveredClub, DiscoveredTeam
from src.scraper.club_enrichment import (
    ClubEnricher,
    EnrichmentResult,
    _is_pro_academy,
    apply_enrichment,
)

# ============================================================================
# Test Data / Fixtures
# ============================================================================

MOCK_CLUB_HOMEPAGE = """
<html>
<head>
  <meta property="og:image" content="https://www.tbunited.com/images/logo.png" />
  <meta name="theme-color" content="#003366" />
  <meta name="msapplication-TileColor" content="#CC0000" />
  <meta name="geo.placename" content="Tampa, FL" />
</head>
<body><h1>Tampa Bay United</h1></body>
</html>
"""

MOCK_CLUB_HOMEPAGE_JSONLD = """
<html>
<head>
  <meta property="og:image" content="/images/logo.png" />
  <script type="application/ld+json">
  {
    "address": {
      "addressLocality": "Fort Lauderdale",
      "addressRegion": "FL"
    }
  }
  </script>
</head>
<body></body>
</html>
"""

MOCK_CLUB_HOMEPAGE_MINIMAL = """
<html><head><title>Test FC</title></head><body></body></html>
"""


def _make_club(name: str, **kwargs) -> DiscoveredClub:
    """Helper to create a DiscoveredClub for testing."""
    return DiscoveredClub(
        club_name=name,
        teams=[
            DiscoveredTeam(
                team_name=name,
                division="Florida",
                age_groups=["U14"],
            )
        ],
        **kwargs,
    )


# ============================================================================
# EnrichmentResult Tests
# ============================================================================


class TestEnrichmentResult:
    def test_fields_found_empty(self):
        result = EnrichmentResult(club_name="Test FC")
        assert result.fields_found == 0
        assert result.needs_manual is True

    def test_fields_found_full(self):
        result = EnrichmentResult(
            club_name="Test FC",
            website="https://example.com",
            location="Tampa, FL",
            logo_url="https://example.com/logo.png",
            primary_color="#003366",
            secondary_color="#CC0000",
        )
        assert result.fields_found == 5
        assert result.needs_manual is False

    def test_needs_manual_with_website(self):
        result = EnrichmentResult(
            club_name="Test FC",
            website="https://example.com",
        )
        assert result.needs_manual is False

    def test_needs_manual_without_website(self):
        result = EnrichmentResult(
            club_name="Test FC",
            location="Tampa, FL",
        )
        assert result.needs_manual is True


# ============================================================================
# ClubEnricher._is_likely_club_website Tests
# ============================================================================


class TestIsLikelyClubWebsite:
    def test_domain_contains_name(self):
        assert ClubEnricher._is_likely_club_website(
            "https://www.tbunited.com", "www.tbunited.com", "Tampa Bay United"
        )

    def test_url_path_contains_name(self):
        assert ClubEnricher._is_likely_club_website(
            "https://example.com/tampa-bay-soccer", "example.com", "Tampa Bay United"
        )

    def test_no_match(self):
        assert not ClubEnricher._is_likely_club_website(
            "https://random-site.com/page", "random-site.com", "Tampa Bay United"
        )

    def test_ignores_short_words(self):
        # "FC" and "SC" are short and should be ignored
        assert not ClubEnricher._is_likely_club_website(
            "https://random-fc.com", "random-fc.com", "Test FC"
        )


# ============================================================================
# ClubEnricher._find_logo_url Tests
# ============================================================================


class TestFindLogoUrl:
    def test_og_image(self):
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(MOCK_CLUB_HOMEPAGE, "html.parser")
        url = ClubEnricher._find_logo_url(soup, "https://www.tbunited.com")
        assert url == "https://www.tbunited.com/images/logo.png"

    def test_relative_og_image(self):
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(MOCK_CLUB_HOMEPAGE_JSONLD, "html.parser")
        url = ClubEnricher._find_logo_url(soup, "https://www.example.com")
        assert url == "https://www.example.com/images/logo.png"

    def test_no_logo(self):
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(MOCK_CLUB_HOMEPAGE_MINIMAL, "html.parser")
        url = ClubEnricher._find_logo_url(soup, "https://www.example.com")
        assert url == ""


# ============================================================================
# ClubEnricher._find_location Tests
# ============================================================================


class TestFindLocation:
    def test_geo_placename(self):
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(MOCK_CLUB_HOMEPAGE, "html.parser")
        loc = ClubEnricher._find_location(soup)
        assert loc == "Tampa, FL"

    def test_json_ld_address(self):
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(MOCK_CLUB_HOMEPAGE_JSONLD, "html.parser")
        loc = ClubEnricher._find_location(soup)
        assert loc == "Fort Lauderdale, FL"

    def test_no_location(self):
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(MOCK_CLUB_HOMEPAGE_MINIMAL, "html.parser")
        loc = ClubEnricher._find_location(soup)
        assert loc == ""


# ============================================================================
# ClubEnricher._find_colors_from_meta Tests
# ============================================================================


class TestFindColorsFromMeta:
    def test_theme_and_tile_color(self):
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(MOCK_CLUB_HOMEPAGE, "html.parser")
        primary, secondary = ClubEnricher._find_colors_from_meta(soup)
        assert primary == "#003366"
        assert secondary == "#CC0000"

    def test_no_colors(self):
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(MOCK_CLUB_HOMEPAGE_MINIMAL, "html.parser")
        primary, secondary = ClubEnricher._find_colors_from_meta(soup)
        assert primary == ""
        assert secondary == ""


# ============================================================================
# ClubEnricher._extract_colors Tests
# ============================================================================


class TestExtractColors:
    @pytest.mark.asyncio
    async def test_svg_logo_skipped(self):
        enricher = ClubEnricher()
        result = EnrichmentResult(
            club_name="Test FC",
            logo_url="https://example.com/logo.svg",
        )

        async with httpx.AsyncClient() as client:
            await enricher._extract_colors(client, result)

        assert result.primary_color == ""
        assert "SVG" in result.errors[0]

    @pytest.mark.asyncio
    async def test_download_failure(self):
        enricher = ClubEnricher()
        result = EnrichmentResult(
            club_name="Test FC",
            logo_url="https://example.com/logo.png",
        )

        async with httpx.AsyncClient() as client:
            with patch.object(client, "get", side_effect=httpx.ConnectError("fail")):
                await enricher._extract_colors(client, result)

        assert result.primary_color == ""
        assert any("Failed to download" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_svg_content_type_skipped(self):
        enricher = ClubEnricher()
        result = EnrichmentResult(
            club_name="Test FC",
            logo_url="https://example.com/logo.png",
        )
        mock_response = httpx.Response(
            200,
            content=b"<svg></svg>",
            headers={"content-type": "image/svg+xml"},
            request=httpx.Request("GET", "https://example.com/logo.png"),
        )

        async with httpx.AsyncClient() as client:
            with patch.object(client, "get", return_value=mock_response):
                await enricher._extract_colors(client, result)

        assert result.primary_color == ""
        assert "SVG" in result.errors[0]


# ============================================================================
# Helper to mock Playwright locators
# ============================================================================


def _mock_locator_with_links(hrefs: list[str]) -> MagicMock:
    """Create a mock Playwright locator that returns link elements."""
    mock_elements = []
    for href in hrefs:
        el = AsyncMock()
        el.get_attribute = AsyncMock(return_value=href)
        mock_elements.append(el)

    mock_locator = AsyncMock()
    mock_locator.all = AsyncMock(return_value=mock_elements)
    return mock_locator


# ============================================================================
# ClubEnricher._search_website Tests (mocked Playwright)
# ============================================================================


def _make_mock_page(link_hrefs: list[str]) -> MagicMock:
    """Create a mock Playwright page with goto (async) and locator (sync)."""
    page = MagicMock()
    page.goto = AsyncMock()
    page.locator = MagicMock(return_value=_mock_locator_with_links(link_hrefs))
    return page


class TestSearchWebsite:
    @pytest.mark.asyncio
    async def test_finds_website_from_startpage(self):
        enricher = ClubEnricher()

        mock_page = _make_mock_page(
            [
                "https://www.tbunited.com/about",
                "https://www.mlssoccer.com/clubs/tampa",
            ]
        )

        url = await enricher._search_website(mock_page, "Tampa Bay United")
        assert url == "https://www.tbunited.com"

    @pytest.mark.asyncio
    async def test_skips_aggregator_domains(self):
        enricher = ClubEnricher()

        mock_page = _make_mock_page(
            [
                "https://www.mlssoccer.com/clubs/test",
                "https://www.facebook.com/testfc",
                "https://www.realclub.com/page",
            ]
        )

        url = await enricher._search_website(mock_page, "Test Club")
        assert url == "https://www.realclub.com"

    @pytest.mark.asyncio
    async def test_no_results(self):
        enricher = ClubEnricher()
        mock_page = _make_mock_page([])

        url = await enricher._search_website(mock_page, "Nonexistent FC")
        assert url == ""

    @pytest.mark.asyncio
    async def test_returns_homepage_not_subpage(self):
        enricher = ClubEnricher()

        mock_page = _make_mock_page(
            [
                "https://www.chargerssoccer.com/mls-next/teams/u14",
            ]
        )

        url = await enricher._search_website(mock_page, "Chargers Soccer Club")
        assert url == "https://www.chargerssoccer.com"

    @pytest.mark.asyncio
    async def test_tries_multiple_queries(self):
        enricher = ClubEnricher()

        page = MagicMock()
        page.goto = AsyncMock()
        call_count = 0

        def make_locator(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                return _mock_locator_with_links([])
            return _mock_locator_with_links(["https://www.intermiamicf.com/youth"])

        page.locator = MagicMock(side_effect=make_locator)

        url = await enricher._search_website(page, "Inter Miami CF")
        assert url == "https://www.intermiamicf.com"
        assert call_count >= 2  # Tried multiple queries

    @pytest.mark.asyncio
    async def test_handles_playwright_error(self):
        enricher = ClubEnricher()

        page = MagicMock()
        page.goto = AsyncMock(side_effect=Exception("Browser crashed"))

        url = await enricher._search_website(page, "Test FC")
        assert url == ""


# ============================================================================
# apply_enrichment Tests
# ============================================================================


class TestApplyEnrichment:
    def test_applies_missing_fields(self):
        clubs = [_make_club("Test FC")]
        results = [
            EnrichmentResult(
                club_name="Test FC",
                website="https://testfc.com",
                location="Tampa, FL",
                logo_url="https://testfc.com/logo.png",
                primary_color="#003366",
                secondary_color="#CC0000",
            )
        ]

        enriched = apply_enrichment(clubs, results)
        assert enriched[0].website == "https://testfc.com"
        assert enriched[0].location == "Tampa, FL"
        assert enriched[0].logo_url == "https://testfc.com/logo.png"
        assert enriched[0].primary_color == "#003366"
        assert enriched[0].secondary_color == "#CC0000"

    def test_preserves_existing_fields(self):
        clubs = [
            _make_club(
                "Test FC",
                website="https://original.com",
                location="Orlando, FL",
            )
        ]
        results = [
            EnrichmentResult(
                club_name="Test FC",
                website="https://different.com",
                location="Tampa, FL",
                logo_url="https://different.com/logo.png",
            )
        ]

        enriched = apply_enrichment(clubs, results)
        # Existing fields should NOT be overwritten
        assert enriched[0].website == "https://original.com"
        assert enriched[0].location == "Orlando, FL"
        # But new fields should be applied
        assert enriched[0].logo_url == "https://different.com/logo.png"

    def test_preserves_teams(self):
        clubs = [_make_club("Test FC")]
        results = [EnrichmentResult(club_name="Test FC")]

        enriched = apply_enrichment(clubs, results)
        assert len(enriched[0].teams) == 1
        assert enriched[0].teams[0].team_name == "Test FC"


# ============================================================================
# Enrich CLI Command Tests
# ============================================================================


class TestEnrichCLI:
    def setup_method(self):
        from typer.testing import CliRunner

        self.runner = CliRunner(env={"NO_COLOR": "1"})

    def test_enrich_missing_input(self):
        from src.cli.main import app

        result = self.runner.invoke(app, ["enrich", "--input", "nonexistent.json"])
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_enrich_empty_clubs(self):
        from src.cli.main import app

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            json.dump([], f)
            tmp_path = f.name

        try:
            result = self.runner.invoke(app, ["enrich", "--input", tmp_path])
            assert result.exit_code == 0
            assert "No clubs found" in result.output
        finally:
            os.unlink(tmp_path)

    def test_enrich_success(self):
        from src.cli.main import app

        clubs_data = [
            {
                "club_name": "Test FC",
                "location": "",
                "website": "",
                "logo_url": "",
                "primary_color": "",
                "secondary_color": "",
                "teams": [
                    {
                        "team_name": "Test FC",
                        "league": "Homegrown",
                        "division": "Florida",
                        "age_groups": ["U14"],
                    }
                ],
            }
        ]

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            json.dump(clubs_data, f)
            input_path = f.name

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            output_path = f.name

        try:
            mock_results = [
                EnrichmentResult(
                    club_name="Test FC",
                    website="https://testfc.com",
                    location="Tampa, FL",
                )
            ]

            with patch(
                "src.scraper.club_enrichment.ClubEnricher.enrich_clubs",
                new_callable=AsyncMock,
                return_value=mock_results,
            ):
                result = self.runner.invoke(
                    app,
                    [
                        "enrich",
                        "--input",
                        input_path,
                        "--output",
                        output_path,
                    ],
                )
                assert result.exit_code == 0
                assert "Saved to" in result.output

                # Verify output JSON
                with open(output_path) as fh:
                    data = json.load(fh)
                assert len(data) == 1
                assert data[0]["website"] == "https://testfc.com"
                assert data[0]["location"] == "Tampa, FL"
        finally:
            os.unlink(input_path)
            os.unlink(output_path)

    def test_enrich_malformed_json(self):
        from src.cli.main import app

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            f.write("not valid json {{{")
            tmp_path = f.name

        try:
            result = self.runner.invoke(app, ["enrich", "--input", tmp_path])
            assert result.exit_code == 1
            assert "Failed to parse" in result.output
        finally:
            os.unlink(tmp_path)

    def test_enrich_shows_manual_count(self):
        from src.cli.main import app

        clubs_data = [
            {
                "club_name": "Missing FC",
                "teams": [
                    {
                        "team_name": "Missing FC",
                        "division": "Florida",
                        "age_groups": ["U14"],
                    }
                ],
            }
        ]

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            json.dump(clubs_data, f)
            input_path = f.name

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            output_path = f.name

        try:
            mock_results = [EnrichmentResult(club_name="Missing FC")]  # no website

            with patch(
                "src.scraper.club_enrichment.ClubEnricher.enrich_clubs",
                new_callable=AsyncMock,
                return_value=mock_results,
            ):
                result = self.runner.invoke(
                    app, ["enrich", "--input", input_path, "--output", output_path]
                )
                assert result.exit_code == 0
                assert "manual enrichment" in result.output
        finally:
            os.unlink(input_path)
            os.unlink(output_path)

    def test_enrich_shows_errors(self):
        from src.cli.main import app

        clubs_data = [
            {
                "club_name": "Error FC",
                "teams": [
                    {
                        "team_name": "Error FC",
                        "division": "Florida",
                        "age_groups": ["U14"],
                    }
                ],
            }
        ]

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            json.dump(clubs_data, f)
            input_path = f.name

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            output_path = f.name

        try:
            mock_results = [
                EnrichmentResult(
                    club_name="Error FC",
                    website="https://errorfc.com",
                    errors=["Failed to download logo: timeout"],
                )
            ]

            with patch(
                "src.scraper.club_enrichment.ClubEnricher.enrich_clubs",
                new_callable=AsyncMock,
                return_value=mock_results,
            ):
                result = self.runner.invoke(
                    app, ["enrich", "--input", input_path, "--output", output_path]
                )
                assert result.exit_code == 0
                assert "Failed to download logo" in result.output
        finally:
            os.unlink(input_path)
            os.unlink(output_path)

    def test_enrich_exception_from_enricher(self):
        from src.cli.main import app

        clubs_data = [
            {
                "club_name": "Crash FC",
                "teams": [
                    {
                        "team_name": "Crash FC",
                        "division": "Florida",
                        "age_groups": ["U14"],
                    }
                ],
            }
        ]

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            json.dump(clubs_data, f)
            input_path = f.name

        try:
            with patch(
                "src.scraper.club_enrichment.ClubEnricher.enrich_clubs",
                new_callable=AsyncMock,
                side_effect=RuntimeError("browser crashed"),
            ):
                result = self.runner.invoke(
                    app, ["enrich", "--input", input_path, "--output", "/tmp/out.json"]
                )
                assert result.exit_code == 1
        finally:
            os.unlink(input_path)


# ============================================================================
# _is_pro_academy Tests
# ============================================================================


class TestIsProAcademy:
    def test_known_mls_club(self):
        assert _is_pro_academy("LA Galaxy")
        assert _is_pro_academy("Inter Miami CF")
        assert _is_pro_academy("New England Revolution")

    def test_case_insensitive(self):
        assert _is_pro_academy("la galaxy")
        assert _is_pro_academy("LA GALAXY")

    def test_unknown_club(self):
        assert not _is_pro_academy("Tampa Bay United")
        assert not _is_pro_academy("Test FC")

    def test_whitespace_stripped(self):
        assert _is_pro_academy("  LA Galaxy  ")


# ============================================================================
# ClubEnricher._normalize_instagram_url Tests
# ============================================================================


class TestNormalizeInstagramUrl:
    def test_valid_profile(self):
        url = ClubEnricher._normalize_instagram_url(
            "https://www.instagram.com/tbunited"
        )
        assert url == "https://www.instagram.com/tbunited"

    def test_profile_with_trailing_slash(self):
        url = ClubEnricher._normalize_instagram_url(
            "https://www.instagram.com/tbunited/"
        )
        assert url == "https://www.instagram.com/tbunited"

    def test_skips_post_urls(self):
        url = ClubEnricher._normalize_instagram_url(
            "https://www.instagram.com/p/abc123/"
        )
        assert url == ""

    def test_skips_reel_urls(self):
        url = ClubEnricher._normalize_instagram_url(
            "https://www.instagram.com/reel/xyz/"
        )
        assert url == ""

    def test_skips_explore(self):
        url = ClubEnricher._normalize_instagram_url(
            "https://www.instagram.com/explore/"
        )
        assert url == ""

    def test_non_instagram_url(self):
        url = ClubEnricher._normalize_instagram_url("https://www.facebook.com/tbunited")
        assert url == ""

    def test_empty_path(self):
        url = ClubEnricher._normalize_instagram_url("https://www.instagram.com/")
        assert url == ""


# ============================================================================
# ClubEnricher._find_instagram_on_page Tests
# ============================================================================


class TestFindInstagramOnPage:
    def test_finds_instagram_link(self):
        from bs4 import BeautifulSoup

        html = '<html><body><a href="https://www.instagram.com/tbunited">IG</a></body></html>'
        soup = BeautifulSoup(html, "html.parser")
        result = ClubEnricher._find_instagram_on_page(soup)
        assert result == "https://www.instagram.com/tbunited"

    def test_skips_post_links(self):
        from bs4 import BeautifulSoup

        html = '<html><body><a href="https://www.instagram.com/p/abc123/">Post</a></body></html>'
        soup = BeautifulSoup(html, "html.parser")
        result = ClubEnricher._find_instagram_on_page(soup)
        assert result == ""

    def test_no_instagram_link(self):
        from bs4 import BeautifulSoup

        html = '<html><body><a href="https://www.facebook.com/tbunited">FB</a></body></html>'
        soup = BeautifulSoup(html, "html.parser")
        result = ClubEnricher._find_instagram_on_page(soup)
        assert result == ""


# ============================================================================
# ClubEnricher._extract_metadata Tests
# ============================================================================


class TestExtractMetadata:
    @pytest.mark.asyncio
    async def test_full_metadata_extraction(self):
        enricher = ClubEnricher()
        result = EnrichmentResult(
            club_name="Tampa Bay United", website="https://www.tbunited.com"
        )

        mock_response = httpx.Response(
            200,
            text=MOCK_CLUB_HOMEPAGE,
            request=httpx.Request("GET", "https://www.tbunited.com"),
        )

        async with httpx.AsyncClient() as client:
            with patch.object(client, "get", return_value=mock_response):
                await enricher._extract_metadata(client, result)

        assert result.logo_url == "https://www.tbunited.com/images/logo.png"
        assert result.location == "Tampa, FL"
        assert result.primary_color == "#003366"
        assert result.secondary_color == "#CC0000"

    @pytest.mark.asyncio
    async def test_http_error(self):
        enricher = ClubEnricher()
        result = EnrichmentResult(club_name="Test FC", website="https://example.com")

        async with httpx.AsyncClient() as client:
            with patch.object(
                client, "get", side_effect=httpx.ConnectError("connection refused")
            ):
                await enricher._extract_metadata(client, result)

        assert any("Failed to fetch" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_instagram_found_on_page(self):
        enricher = ClubEnricher()
        result = EnrichmentResult(club_name="Test FC", website="https://example.com")

        html_with_ig = '<html><body><a href="https://www.instagram.com/testfc">IG</a></body></html>'
        mock_response = httpx.Response(
            200,
            text=html_with_ig,
            request=httpx.Request("GET", "https://example.com"),
        )

        async with httpx.AsyncClient() as client:
            with patch.object(client, "get", return_value=mock_response):
                await enricher._extract_metadata(client, result)

        assert result.instagram == "https://www.instagram.com/testfc"

    @pytest.mark.asyncio
    async def test_existing_location_not_overwritten(self):
        enricher = ClubEnricher()
        result = EnrichmentResult(
            club_name="Test FC",
            website="https://example.com",
            location="Original City, FL",
        )

        mock_response = httpx.Response(
            200,
            text=MOCK_CLUB_HOMEPAGE,
            request=httpx.Request("GET", "https://example.com"),
        )

        async with httpx.AsyncClient() as client:
            with patch.object(client, "get", return_value=mock_response):
                await enricher._extract_metadata(client, result)

        assert result.location == "Original City, FL"


# ============================================================================
# ClubEnricher._search_instagram Tests
# ============================================================================


class TestSearchInstagram:
    @pytest.mark.asyncio
    async def test_finds_instagram(self):
        enricher = ClubEnricher()

        mock_elements = []
        el = AsyncMock()
        el.get_attribute = AsyncMock(return_value="https://www.instagram.com/tbunited")
        mock_elements.append(el)

        mock_locator = AsyncMock()
        mock_locator.all = AsyncMock(return_value=mock_elements)

        page = MagicMock()
        page.goto = AsyncMock()
        page.locator = MagicMock(return_value=mock_locator)

        result = await enricher._search_instagram(page, "Tampa Bay United")
        assert result == "https://www.instagram.com/tbunited"

    @pytest.mark.asyncio
    async def test_no_instagram_found(self):
        enricher = ClubEnricher()

        mock_locator = AsyncMock()
        mock_locator.all = AsyncMock(return_value=[])

        page = MagicMock()
        page.goto = AsyncMock()
        page.locator = MagicMock(return_value=mock_locator)

        result = await enricher._search_instagram(page, "Unknown Club")
        assert result == ""

    @pytest.mark.asyncio
    async def test_handles_error(self):
        enricher = ClubEnricher()

        page = MagicMock()
        page.goto = AsyncMock(side_effect=Exception("network error"))

        result = await enricher._search_instagram(page, "Test FC")
        assert result == ""


# ============================================================================
# ClubEnricher.enrich_clubs Tests
# ============================================================================


class TestEnrichClubs:
    @pytest.mark.asyncio
    async def test_skip_existing(self):
        enricher = ClubEnricher()
        club = _make_club(
            "Tampa Bay United",
            website="https://tbunited.com",
            location="Tampa, FL",
        )

        with patch.object(
            enricher, "_enrich_one", new_callable=AsyncMock
        ) as mock_enrich:
            with patch("src.scraper.club_enrichment.async_playwright") as mock_pw:
                mock_context = AsyncMock()
                mock_browser = AsyncMock()
                mock_page = AsyncMock()
                mock_browser.new_context = AsyncMock(return_value=mock_context)
                mock_context.new_page = AsyncMock(return_value=mock_page)
                mock_pw.return_value.__aenter__ = AsyncMock(return_value=mock_pw)
                mock_pw.chromium = MagicMock()
                mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)

                with patch("httpx.AsyncClient") as mock_http:
                    mock_http_instance = AsyncMock()
                    mock_http.return_value.__aenter__ = AsyncMock(
                        return_value=mock_http_instance
                    )
                    mock_http.return_value.__aexit__ = AsyncMock(return_value=False)

                    results = await enricher.enrich_clubs([club], skip_existing=True)

        # _enrich_one should NOT be called — club already has a website
        mock_enrich.assert_not_called()
        assert len(results) == 1
        assert results[0].website == "https://tbunited.com"

    @pytest.mark.asyncio
    async def test_progress_callback(self):
        enricher = ClubEnricher()
        club = _make_club("Test FC")

        progress_calls = []

        def on_progress(name, result):
            progress_calls.append(name)

        enricher.on_progress = on_progress

        mock_result = EnrichmentResult(
            club_name="Test FC", website="https://testfc.com"
        )

        with patch.object(
            enricher, "_enrich_one", new_callable=AsyncMock, return_value=mock_result
        ):
            with patch("src.scraper.club_enrichment.async_playwright") as mock_pw:
                mock_context = AsyncMock()
                mock_browser = AsyncMock()
                mock_page = AsyncMock()
                mock_browser.new_context = AsyncMock(return_value=mock_context)
                mock_context.new_page = AsyncMock(return_value=mock_page)
                mock_pw.return_value.__aenter__ = AsyncMock(return_value=mock_pw)
                mock_pw.chromium = MagicMock()
                mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)

                with patch("httpx.AsyncClient") as mock_http:
                    mock_http_instance = AsyncMock()
                    mock_http.return_value.__aenter__ = AsyncMock(
                        return_value=mock_http_instance
                    )
                    mock_http.return_value.__aexit__ = AsyncMock(return_value=False)

                    results = await enricher.enrich_clubs([club])

        assert results[0].website == "https://testfc.com"
        assert "Test FC" in progress_calls


# ============================================================================
# apply_enrichment — pro academy flag Tests
# ============================================================================


class TestApplyEnrichmentProAcademy:
    def test_sets_pro_academy_flag(self):
        clubs = [_make_club("LA Galaxy")]
        results = [EnrichmentResult(club_name="LA Galaxy", is_pro_academy=True)]

        enriched = apply_enrichment(clubs, results)
        assert enriched[0].is_pro_academy is True

    def test_instagram_applied(self):
        clubs = [_make_club("Test FC")]
        results = [
            EnrichmentResult(
                club_name="Test FC",
                instagram="https://www.instagram.com/testfc",
            )
        ]

        enriched = apply_enrichment(clubs, results)
        assert enriched[0].instagram == "https://www.instagram.com/testfc"
