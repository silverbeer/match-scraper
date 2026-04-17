"""Club enrichment module — populates website, location, logo, colors, and Instagram for clubs.

Uses Playwright-based Startpage search for reliable website discovery, then
httpx/BeautifulSoup for metadata extraction and colorthief for logo color analysis.
"""

import asyncio
import io
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from playwright.async_api import Page, async_playwright

from src.models.discovery import DiscoveredClub

logger = logging.getLogger(__name__)

# Request configuration
DEFAULT_TIMEOUT = 15.0
DEFAULT_DELAY = 3.0

# User-Agent for httpx requests (metadata/logo fetching)
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Domains to skip as they're aggregators, not club websites
SKIP_DOMAINS = {
    "mlssoccer.com",
    "mlsnextpro.com",
    "ussoccer.com",
    "topdrawersoccer.com",
    "gotsoccer.com",
    "soccerwire.com",
    "wikipedia.org",
    "facebook.com",
    "instagram.com",
    "twitter.com",
    "x.com",
    "youtube.com",
    "linkedin.com",
    "yelp.com",
    "tiktok.com",
    "pinterest.com",
    "reddit.com",
    "niche.com",
    "transfermarkt.com",
    "google.com",
    "bing.com",
}

# MLS Pro Academy clubs — sourced from https://www.mlssoccer.com/standings/
# Includes common name variations for matching against discovered club names.
MLS_PRO_ACADEMIES = {
    "Atlanta United",
    "Atlanta United FC",
    "Austin FC",
    "Charlotte FC",
    "Charlotte Football Club",
    "Chicago Fire",
    "Chicago Fire FC",
    "FC Cincinnati",
    "Colorado Rapids",
    "Columbus Crew",
    "FC Dallas",
    "D.C. United",
    "DC United",
    "Houston Dynamo",
    "Houston Dynamo FC",
    "Sporting Kansas City",
    "LA Galaxy",
    "Los Angeles Galaxy",
    "LAFC",
    "Los Angeles FC",
    "Inter Miami CF",
    "Minnesota United",
    "Minnesota United FC",
    "CF Montréal",
    "CF Montreal",
    "Nashville SC",
    "New England Revolution",
    "New York City FC",
    "NYCFC",
    "New York Red Bulls",
    "Red Bull New York",
    "Orlando City SC",
    "Orlando City",
    "Philadelphia Union",
    "Portland Timbers",
    "Real Salt Lake",
    "San Diego FC",
    "San Jose Earthquakes",
    "Seattle Sounders",
    "Seattle Sounders FC",
    "St. Louis City SC",
    "St. Louis CITY SC",
    "Toronto FC",
    "Vancouver Whitecaps",
    "Vancouver Whitecaps FC",
}

# Lowercase lookup for efficient matching
_MLS_PRO_ACADEMIES_LOWER = {name.lower() for name in MLS_PRO_ACADEMIES}

# Search engine base URL (Startpage — privacy-focused, no CAPTCHAs, Google results)
SEARCH_URL = "https://www.startpage.com/sp/search"

# Multiple search query templates, tried in order
SEARCH_QUERIES = [
    '"{club_name}" soccer club official website',
    '"{club_name}" MLS Next youth soccer',
    "{club_name} soccer club",
]


@dataclass
class EnrichmentResult:
    """Result of enriching a single club."""

    club_name: str
    website: str = ""
    location: str = ""
    logo_url: str = ""
    primary_color: str = ""
    secondary_color: str = ""
    instagram: str = ""
    is_pro_academy: bool = False
    errors: list[str] = field(default_factory=list)

    @property
    def fields_found(self) -> int:
        """Count of non-empty enriched fields."""
        count = 0
        if self.website:
            count += 1
        if self.location:
            count += 1
        if self.logo_url:
            count += 1
        if self.primary_color:
            count += 1
        if self.secondary_color:
            count += 1
        if self.instagram:
            count += 1
        return count

    @property
    def needs_manual(self) -> bool:
        """Whether this club needs manual enrichment."""
        return not self.website


def _is_pro_academy(club_name: str) -> bool:
    """Check if a club name matches a known MLS pro academy."""
    return club_name.lower().strip() in _MLS_PRO_ACADEMIES_LOWER


class ClubEnricher:
    """Enriches discovered clubs with website, location, logo, and brand colors.

    Pipeline:
        1. Search Google via Playwright for the club's website
        2. Fetch the homepage with httpx, extract metadata (og:image, theme-color, geo tags)
        3. Download logo and extract dominant colors via colorthief
    """

    def __init__(
        self,
        delay: float = DEFAULT_DELAY,
        timeout: float = DEFAULT_TIMEOUT,
        headless: bool = True,
        on_progress: Optional[object] = None,
    ) -> None:
        self.delay = delay
        self.timeout = timeout
        self.headless = headless
        self.on_progress = on_progress

    async def enrich_clubs(
        self,
        clubs: list[DiscoveredClub],
        skip_existing: bool = False,
    ) -> list[EnrichmentResult]:
        """Enrich a list of clubs sequentially using a single browser session.

        Args:
            clubs: List of discovered clubs to enrich.
            skip_existing: If True, skip clubs that already have a website.

        Returns:
            List of EnrichmentResult objects (same order as input).
        """
        results: list[EnrichmentResult] = []

        async with httpx.AsyncClient(
            timeout=self.timeout,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        ) as http_client:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(
                    headless=self.headless,
                    args=["--no-sandbox", "--disable-setuid-sandbox"],
                )
                context = await browser.new_context(
                    user_agent=USER_AGENT,
                    viewport={"width": 1280, "height": 720},
                )
                page = await context.new_page()

                # Warm up the search engine session
                await self._warm_up_search(page)

                for i, club in enumerate(clubs):
                    if skip_existing and club.website:
                        results.append(
                            EnrichmentResult(
                                club_name=club.club_name,
                                website=club.website,
                                location=club.location,
                                logo_url=club.logo_url,
                                primary_color=club.primary_color,
                                secondary_color=club.secondary_color,
                                instagram=club.instagram,
                                is_pro_academy=_is_pro_academy(club.club_name),
                            )
                        )
                        continue

                    logger.info(
                        "Enriching club %d/%d: %s", i + 1, len(clubs), club.club_name
                    )
                    result = await self._enrich_one(page, http_client, club)
                    results.append(result)

                    # Report progress
                    if self.on_progress:
                        self.on_progress(club.club_name, result)  # type: ignore[operator]

                    # Rate-limit between clubs
                    if i < len(clubs) - 1:
                        await asyncio.sleep(self.delay)

                await context.close()
                await browser.close()

        return results

    async def _warm_up_search(self, page: Page) -> None:
        """Navigate to the search engine to initialize cookies/session."""
        try:
            await page.goto(SEARCH_URL, wait_until="domcontentloaded")
            await asyncio.sleep(1)
        except Exception as e:
            logger.debug("Search engine warmup: %s", e)

    async def _enrich_one(
        self,
        page: Page,
        http_client: httpx.AsyncClient,
        club: DiscoveredClub,
    ) -> EnrichmentResult:
        """Enrich a single club through the full pipeline."""
        result = EnrichmentResult(club_name=club.club_name)

        # Check if this is an MLS pro academy
        result.is_pro_academy = _is_pro_academy(club.club_name)

        # Carry over any existing data
        if club.location:
            result.location = club.location
        if club.instagram:
            result.instagram = club.instagram

        # Step 1: Find website via Google search (Playwright)
        website = await self._search_website(page, club.club_name)
        if not website:
            result.errors.append("No website found via search")
            # Still try to find Instagram even without a website
            if not result.instagram:
                instagram = await self._search_instagram(page, club.club_name)
                if instagram:
                    result.instagram = instagram
            return result
        result.website = website

        # Step 2: Fetch homepage and extract metadata (httpx)
        await self._extract_metadata(http_client, result)

        # Step 3: Extract colors from logo (httpx + colorthief)
        if result.logo_url:
            await self._extract_colors(http_client, result)

        # Step 4: Find Instagram (from homepage links or Google search)
        if not result.instagram:
            instagram = await self._search_instagram(page, club.club_name)
            if instagram:
                result.instagram = instagram

        return result

    async def _search_website(
        self,
        page: Page,
        club_name: str,
    ) -> str:
        """Search Google via Playwright for the club's website.

        Tries multiple query templates. Returns the first non-aggregator result URL.
        """
        for query_template in SEARCH_QUERIES:
            query = query_template.format(club_name=club_name)
            url = await self._startpage_search(page, query, club_name)
            if url:
                return url

        return ""

    async def _startpage_search(
        self,
        page: Page,
        query: str,
        club_name: str,
    ) -> str:
        """Execute a single Startpage search and return the best result URL."""
        try:
            search_url = f"{SEARCH_URL}?q={query}"
            await page.goto(search_url, wait_until="domcontentloaded")
            await asyncio.sleep(2)

            # Extract search result links using Playwright locators
            link_elements = await page.locator(
                "a.w-gl__result-url, a.result-link, .w-gl__result a"
            ).all()
            results = []
            for link in link_elements:
                href = await link.get_attribute("href")
                if href and href.startswith("http") and "startpage" not in href:
                    results.append(href)

            # Deduplicate while preserving order
            seen: set[str] = set()
            unique_results = []
            for url in results:
                if url not in seen:
                    seen.add(url)
                    unique_results.append(url)
            results = unique_results[:15]

            if not results:
                logger.debug("No search results for query: %s", query)
                return ""

            # Filter and validate results
            for url in results:
                parsed = urlparse(url)
                domain = parsed.netloc.lower()

                # Skip aggregator domains
                if any(skip in domain for skip in SKIP_DOMAINS):
                    continue

                # Skip Google cache/translate links
                if "google.com" in domain or "googleapis.com" in domain:
                    continue

                # Basic relevance check: does the URL or domain relate to the club?
                if self._is_likely_club_website(url, domain, club_name):
                    # Normalize to homepage
                    homepage = f"{parsed.scheme}://{parsed.netloc}"
                    return homepage

            # If no strong match, return first non-aggregator result's homepage
            for url in results:
                parsed = urlparse(url)
                domain = parsed.netloc.lower()
                if not any(skip in domain for skip in SKIP_DOMAINS):
                    if "google.com" not in domain and "googleapis.com" not in domain:
                        homepage = f"{parsed.scheme}://{parsed.netloc}"
                        return homepage

            return ""

        except Exception as e:
            logger.warning("Google search failed for '%s': %s", club_name, e)
            return ""

    @staticmethod
    def _is_likely_club_website(url: str, domain: str, club_name: str) -> bool:
        """Heuristic check: does this URL likely belong to the club?"""
        # Normalize club name for comparison
        name_parts = club_name.lower().replace("fc", "").replace("sc", "").split()
        name_parts = [p for p in name_parts if len(p) > 2]

        url_lower = url.lower()
        domain_lower = domain.lower()

        # Check if any significant word from the club name appears in the domain
        for part in name_parts:
            if part in domain_lower:
                return True

        # Check if the URL path contains club name words
        for part in name_parts:
            if part in url_lower:
                return True

        return False

    async def _search_instagram(
        self,
        page: Page,
        club_name: str,
    ) -> str:
        """Search Startpage for the club's Instagram page.

        Returns:
            Instagram URL if found, empty string otherwise.
        """
        query = f'"{club_name}" soccer instagram site:instagram.com'
        try:
            search_url = f"{SEARCH_URL}?q={query}"
            await page.goto(search_url, wait_until="domcontentloaded")
            await asyncio.sleep(2)

            link_elements = await page.locator('a[href*="instagram.com"]').all()
            results = []
            for link in link_elements:
                href = await link.get_attribute("href")
                if href and "instagram.com" in href and "startpage" not in href:
                    results.append(href)

            for url in results:
                # Normalize Instagram URL — extract the profile path
                normalized = self._normalize_instagram_url(url)
                if normalized:
                    return normalized

        except Exception as e:
            logger.debug("Instagram search failed for '%s': %s", club_name, e)

        return ""

    @staticmethod
    def _normalize_instagram_url(url: str) -> str:
        """Normalize an Instagram URL to a clean profile URL.

        Returns:
            Normalized URL like https://www.instagram.com/username or empty string.
        """
        parsed = urlparse(url)
        if "instagram.com" not in parsed.netloc:
            return ""

        # Extract the path, strip query params and trailing slashes
        path = parsed.path.strip("/")
        if not path:
            return ""

        # Skip non-profile pages
        skip_paths = {"p", "reel", "stories", "explore", "accounts", "about"}
        first_segment = path.split("/")[0]
        if first_segment in skip_paths:
            return ""

        # Return clean profile URL (just the username)
        username = path.split("/")[0]
        return f"https://www.instagram.com/{username}"

    @staticmethod
    def _find_instagram_on_page(soup: BeautifulSoup) -> str:
        """Find Instagram link on a club's homepage."""
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if "instagram.com" in href:
                parsed = urlparse(href)
                path = parsed.path.strip("/")
                if path and path.split("/")[0] not in {
                    "p",
                    "reel",
                    "stories",
                    "explore",
                }:
                    username = path.split("/")[0]
                    return f"https://www.instagram.com/{username}"
        return ""

    async def _extract_metadata(
        self,
        client: httpx.AsyncClient,
        result: EnrichmentResult,
    ) -> None:
        """Fetch a club's homepage and extract metadata."""
        try:
            response = await client.get(result.website)
            response.raise_for_status()
        except httpx.HTTPError as e:
            result.errors.append(f"Failed to fetch homepage: {e}")
            return

        soup = BeautifulSoup(response.text, "html.parser")

        # Extract logo URL from og:image or other meta tags
        logo_url = self._find_logo_url(soup, result.website)
        if logo_url:
            result.logo_url = logo_url

        # Extract location from geo tags or structured data
        if not result.location:
            location = self._find_location(soup)
            if location:
                result.location = location

        # Extract Instagram from homepage links
        if not result.instagram:
            instagram = self._find_instagram_on_page(soup)
            if instagram:
                result.instagram = instagram

        # Extract theme color
        primary, secondary = self._find_colors_from_meta(soup)
        if primary:
            result.primary_color = primary
        if secondary:
            result.secondary_color = secondary

    @staticmethod
    def _find_logo_url(soup: BeautifulSoup, base_url: str) -> str:
        """Find a logo URL from HTML metadata."""
        # Try og:image first (most common for club logos)
        og_image = soup.find("meta", property="og:image")
        if og_image and og_image.get("content"):
            url = og_image["content"]
            if url.startswith("/"):
                url = urljoin(base_url, url)
            return url

        # Try Twitter card image
        twitter_image = soup.find("meta", attrs={"name": "twitter:image"})
        if twitter_image and twitter_image.get("content"):
            url = twitter_image["content"]
            if url.startswith("/"):
                url = urljoin(base_url, url)
            return url

        # Try link rel="icon" (favicon — less ideal but better than nothing)
        icon_link = soup.find("link", rel=lambda x: x and "icon" in x)
        if icon_link and icon_link.get("href"):
            url = icon_link["href"]
            if url.startswith("/"):
                url = urljoin(base_url, url)
            # Skip tiny favicons
            sizes = icon_link.get("sizes", "")
            if sizes and sizes != "any":
                try:
                    w = int(sizes.split("x")[0])
                    if w < 64:
                        return ""
                except (ValueError, IndexError):
                    pass
            return url

        return ""

    @staticmethod
    def _find_location(soup: BeautifulSoup) -> str:
        """Extract location from HTML metadata."""
        # Try geo.placename meta tag
        geo = soup.find("meta", attrs={"name": "geo.placename"})
        if geo and geo.get("content"):
            return geo["content"]

        # Try geo.region (usually state code like US-FL)
        geo_region = soup.find("meta", attrs={"name": "geo.region"})
        if geo_region and geo_region.get("content"):
            region = geo_region["content"]
            if "-" in region:
                region = region.split("-")[-1]

        # Try schema.org address in JSON-LD
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                # Handle both single objects and arrays
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    address = item.get("address", {})
                    if isinstance(address, dict):
                        city = address.get("addressLocality", "")
                        state = address.get("addressRegion", "")
                        if city and state:
                            return f"{city}, {state}"
                        if city:
                            return city
            except (json.JSONDecodeError, TypeError):
                continue

        return ""

    @staticmethod
    def _find_colors_from_meta(soup: BeautifulSoup) -> tuple[str, str]:
        """Extract brand colors from HTML meta tags.

        Returns:
            Tuple of (primary_color, secondary_color) as hex strings.
        """
        primary = ""
        secondary = ""

        # Try theme-color meta tag
        theme_color = soup.find("meta", attrs={"name": "theme-color"})
        if theme_color and theme_color.get("content"):
            color = theme_color["content"].strip()
            if re.match(r"^#[0-9a-fA-F]{3,8}$", color):
                primary = color

        # Try msapplication-TileColor
        tile_color = soup.find("meta", attrs={"name": "msapplication-TileColor"})
        if tile_color and tile_color.get("content"):
            color = tile_color["content"].strip()
            if re.match(r"^#[0-9a-fA-F]{3,8}$", color):
                if not primary:
                    primary = color
                elif color != primary:
                    secondary = color

        return primary, secondary

    async def _extract_colors(
        self,
        client: httpx.AsyncClient,
        result: EnrichmentResult,
    ) -> None:
        """Download logo and extract dominant colors using colorthief."""
        # Skip SVG images — colorthief can't process them
        if result.logo_url.lower().endswith(".svg"):
            result.errors.append("Logo is SVG — skipped color extraction")
            return

        try:
            response = await client.get(result.logo_url)
            response.raise_for_status()
        except httpx.HTTPError as e:
            result.errors.append(f"Failed to download logo: {e}")
            return

        # Verify it's an image
        content_type = response.headers.get("content-type", "")
        if "svg" in content_type:
            result.errors.append("Logo is SVG — skipped color extraction")
            return

        try:
            from colorthief import ColorThief

            image_data = io.BytesIO(response.content)
            ct = ColorThief(image_data)

            # Get dominant color as primary (if not already set from meta)
            if not result.primary_color:
                rgb = ct.get_color(quality=1)
                result.primary_color = "#{:02X}{:02X}{:02X}".format(*rgb)

            # Get palette for secondary color (if not already set)
            if not result.secondary_color:
                palette = ct.get_palette(color_count=3, quality=1)
                if len(palette) >= 2:
                    # Use the second most dominant color
                    secondary_rgb = palette[1]
                    result.secondary_color = "#{:02X}{:02X}{:02X}".format(
                        *secondary_rgb
                    )

        except Exception as e:
            result.errors.append(f"Color extraction failed: {e}")


def apply_enrichment(
    clubs: list[DiscoveredClub],
    results: list[EnrichmentResult],
) -> list[DiscoveredClub]:
    """Apply enrichment results back to club objects.

    Only overwrites empty fields — never clobbers existing data.

    Returns:
        New list of DiscoveredClub objects with enriched fields.
    """
    enriched = []
    for club, result in zip(clubs, results):
        data = club.model_dump()

        if not data["website"] and result.website:
            data["website"] = result.website
        if not data["location"] and result.location:
            data["location"] = result.location
        if not data["logo_url"] and result.logo_url:
            data["logo_url"] = result.logo_url
        if not data["primary_color"] and result.primary_color:
            data["primary_color"] = result.primary_color
        if not data["secondary_color"] and result.secondary_color:
            data["secondary_color"] = result.secondary_color
        if not data["instagram"] and result.instagram:
            data["instagram"] = result.instagram
        if result.is_pro_academy:
            data["is_pro_academy"] = True

        enriched.append(DiscoveredClub(**data))

    return enriched
