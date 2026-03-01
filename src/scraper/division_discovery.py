"""Division discovery module.

Discovers clubs and teams in a given division by scraping match data
across all age groups and extracting unique team names.
"""

from datetime import date

from ..models.discovery import DiscoveredClub, DiscoveredTeam
from ..utils.logger import get_logger
from .config import ScrapingConfig
from .mls_scraper import MLSScraper, MLSScraperError

logger = get_logger()

# Standard HG age groups on MLS Next
DISCOVERY_AGE_GROUPS = ["U13", "U14", "U15", "U16", "U17", "U19"]

# Full season date range for discovery (cast the widest net)
SEASON_START = date(2025, 9, 1)
SEASON_END = date(2026, 6, 30)


class DivisionDiscoverer:
    """Discovers clubs/teams in a division by scraping all age groups."""

    def __init__(
        self,
        division: str,
        league: str = "Homegrown",
        headless: bool = True,
        age_groups: list[str] | None = None,
    ):
        self.division = division
        self.league = league
        self.headless = headless
        self.age_groups = age_groups or DISCOVERY_AGE_GROUPS

    async def discover(self) -> list[DiscoveredClub]:
        """Run discovery across all age groups and return clubs.json-compatible output.

        For each age group, launches a separate browser session to scrape all
        matches in the division. Team names are collected from both home_team
        and away_team fields. Results are aggregated into a club list with
        per-club age group coverage.

        Returns:
            List of DiscoveredClub objects ready for clubs.json serialization.
        """
        # team_name -> set of age groups
        team_age_groups: dict[str, set[str]] = {}

        for age_group in self.age_groups:
            logger.info(
                f"Discovering teams for {age_group} {self.league} {self.division}"
            )

            teams = await self._scrape_teams_for_age_group(age_group)
            for team_name in teams:
                if team_name not in team_age_groups:
                    team_age_groups[team_name] = set()
                team_age_groups[team_name].add(age_group)

            logger.info(
                f"{age_group}: found {len(teams)} unique teams "
                f"(running total: {len(team_age_groups)} clubs)"
            )

        return self._build_clubs(team_age_groups)

    async def _scrape_teams_for_age_group(self, age_group: str) -> set[str]:
        """Scrape a single age group and return the set of unique team names."""
        import os

        config = ScrapingConfig(
            age_group=age_group,
            league=self.league,
            division=self.division,
            club="",
            competition="",
            conference="",
            look_back_days=0,
            start_date=SEASON_START,
            end_date=SEASON_END,
            missing_table_api_url=os.getenv(
                "MISSING_TABLE_API_BASE_URL", "http://localhost:8000"
            ),
            missing_table_api_key=os.getenv("MISSING_TABLE_API_TOKEN", "unused"),
            log_level="ERROR",
        )

        scraper = MLSScraper(config, headless=self.headless)
        try:
            matches = await scraper.scrape_matches()
        except MLSScraperError as e:
            logger.warning(f"Scraping failed for {age_group}: {e}")
            return set()

        teams: set[str] = set()
        for match in matches:
            teams.add(match.home_team)
            teams.add(match.away_team)

        return teams

    def _build_clubs(
        self, team_age_groups: dict[str, set[str]]
    ) -> list[DiscoveredClub]:
        """Build clubs.json-compatible output from discovered teams.

        In HG leagues, team_name == club_name. Each club gets a single team
        entry with all discovered age groups.
        """
        clubs: list[DiscoveredClub] = []

        for team_name in sorted(team_age_groups):
            age_groups_sorted = sorted(
                team_age_groups[team_name],
                key=lambda ag: int(ag[1:]),  # sort by numeric part
            )

            club = DiscoveredClub(
                club_name=team_name,
                teams=[
                    DiscoveredTeam(
                        team_name=team_name,
                        league=self.league,
                        division=self.division,
                        age_groups=age_groups_sorted,
                    )
                ],
            )
            clubs.append(club)

        return clubs
