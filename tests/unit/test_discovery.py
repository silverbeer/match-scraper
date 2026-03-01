"""Unit tests for discovery models and division discovery module."""

import json
import os
import tempfile
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from src.models.discovery import DiscoveredClub, DiscoveredTeam
from src.scraper.division_discovery import (
    DISCOVERY_AGE_GROUPS,
    SEASON_END,
    SEASON_START,
    DivisionDiscoverer,
)
from src.scraper.mls_scraper import MLSScraperError
from src.scraper.models import Match


class TestDiscoveredTeam:
    """Test cases for DiscoveredTeam Pydantic model."""

    def test_basic_creation(self):
        team = DiscoveredTeam(
            team_name="Inter Miami CF",
            league="Homegrown",
            division="Florida",
            age_groups=["U14", "U15"],
        )
        assert team.team_name == "Inter Miami CF"
        assert team.league == "Homegrown"
        assert team.division == "Florida"
        assert team.age_groups == ["U14", "U15"]

    def test_defaults(self):
        team = DiscoveredTeam(team_name="Test FC", division="Florida")
        assert team.league == "Homegrown"
        assert team.age_groups == []

    def test_serialization(self):
        team = DiscoveredTeam(
            team_name="Orlando City SC",
            division="Florida",
            age_groups=["U13", "U14"],
        )
        data = team.model_dump()
        assert data["team_name"] == "Orlando City SC"
        assert data["division"] == "Florida"
        assert data["age_groups"] == ["U13", "U14"]


class TestDiscoveredClub:
    """Test cases for DiscoveredClub Pydantic model."""

    def test_basic_creation(self):
        club = DiscoveredClub(
            club_name="Inter Miami CF",
            location="Fort Lauderdale, FL",
            website="https://www.intermiamicf.com",
            teams=[
                DiscoveredTeam(
                    team_name="Inter Miami CF",
                    division="Florida",
                    age_groups=["U14", "U15"],
                )
            ],
        )
        assert club.club_name == "Inter Miami CF"
        assert club.location == "Fort Lauderdale, FL"
        assert len(club.teams) == 1

    def test_defaults(self):
        club = DiscoveredClub(club_name="Test FC")
        assert club.location == ""
        assert club.website == ""
        assert club.teams == []

    def test_serialization_clubs_json_compatible(self):
        """Test that serialized output matches clubs.json format."""
        club = DiscoveredClub(
            club_name="Orlando City SC",
            teams=[
                DiscoveredTeam(
                    team_name="Orlando City SC",
                    league="Homegrown",
                    division="Florida",
                    age_groups=["U13", "U14", "U15"],
                )
            ],
        )
        data = club.model_dump()
        assert "club_name" in data
        assert "location" in data
        assert "website" in data
        assert "teams" in data
        assert data["teams"][0]["team_name"] == "Orlando City SC"
        assert data["teams"][0]["league"] == "Homegrown"
        assert data["teams"][0]["division"] == "Florida"


class TestDivisionDiscoverer:
    """Test cases for DivisionDiscoverer."""

    def test_init_defaults(self):
        discoverer = DivisionDiscoverer(division="Florida")
        assert discoverer.division == "Florida"
        assert discoverer.league == "Homegrown"
        assert discoverer.headless is True
        assert discoverer.age_groups == DISCOVERY_AGE_GROUPS

    def test_init_custom_age_groups(self):
        discoverer = DivisionDiscoverer(division="Florida", age_groups=["U14", "U15"])
        assert discoverer.age_groups == ["U14", "U15"]

    def test_season_constants(self):
        assert SEASON_START.year == 2025
        assert SEASON_START.month == 9
        assert SEASON_END.year == 2026
        assert SEASON_END.month == 6

    def test_build_clubs_empty(self):
        discoverer = DivisionDiscoverer(division="Florida")
        clubs = discoverer._build_clubs({})
        assert clubs == []

    def test_build_clubs_single_team(self):
        discoverer = DivisionDiscoverer(division="Florida")
        team_age_groups = {"Inter Miami CF": {"U14", "U15"}}
        clubs = discoverer._build_clubs(team_age_groups)

        assert len(clubs) == 1
        assert clubs[0].club_name == "Inter Miami CF"
        assert clubs[0].teams[0].team_name == "Inter Miami CF"
        assert clubs[0].teams[0].division == "Florida"
        assert clubs[0].teams[0].league == "Homegrown"
        assert clubs[0].teams[0].age_groups == ["U14", "U15"]

    def test_build_clubs_multiple_teams_sorted(self):
        discoverer = DivisionDiscoverer(division="Florida")
        team_age_groups = {
            "Orlando City SC": {"U13", "U14"},
            "Inter Miami CF": {"U14", "U15", "U16"},
            "Tampa Bay United": {"U14"},
        }
        clubs = discoverer._build_clubs(team_age_groups)

        assert len(clubs) == 3
        # Should be sorted alphabetically by club name
        assert clubs[0].club_name == "Inter Miami CF"
        assert clubs[1].club_name == "Orlando City SC"
        assert clubs[2].club_name == "Tampa Bay United"

    def test_build_clubs_age_groups_sorted_numerically(self):
        discoverer = DivisionDiscoverer(division="Florida")
        team_age_groups = {"Test FC": {"U17", "U13", "U15", "U14"}}
        clubs = discoverer._build_clubs(team_age_groups)

        assert clubs[0].teams[0].age_groups == ["U13", "U14", "U15", "U17"]

    @pytest.mark.asyncio
    async def test_scrape_teams_for_age_group_failure(self):
        """Test that scraping failure returns empty set."""
        discoverer = DivisionDiscoverer(division="Florida")

        with patch("src.scraper.division_discovery.MLSScraper") as mock_scraper_cls:
            mock_scraper = AsyncMock()
            mock_scraper.scrape_matches.side_effect = MLSScraperError("Browser failed")
            mock_scraper_cls.return_value = mock_scraper

            teams = await discoverer._scrape_teams_for_age_group("U14")
            assert teams == set()

    @pytest.mark.asyncio
    async def test_scrape_teams_for_age_group_success(self):
        """Test successful team extraction from matches."""
        discoverer = DivisionDiscoverer(division="Florida")

        mock_matches = [
            Match(
                match_id="1",
                home_team="Inter Miami CF",
                away_team="Orlando City SC",
                match_datetime=datetime.now() + timedelta(days=1),
            ),
            Match(
                match_id="2",
                home_team="Tampa Bay United",
                away_team="Inter Miami CF",
                match_datetime=datetime.now() + timedelta(days=2),
            ),
        ]

        with patch("src.scraper.division_discovery.MLSScraper") as mock_scraper_cls:
            mock_scraper = AsyncMock()
            mock_scraper.scrape_matches.return_value = mock_matches
            mock_scraper_cls.return_value = mock_scraper

            teams = await discoverer._scrape_teams_for_age_group("U14")
            assert teams == {"Inter Miami CF", "Orlando City SC", "Tampa Bay United"}

    @pytest.mark.asyncio
    async def test_discover_aggregates_age_groups(self):
        """Test that discover aggregates teams across age groups."""
        discoverer = DivisionDiscoverer(division="Florida", age_groups=["U14", "U15"])

        u14_matches = [
            Match(
                match_id="1",
                home_team="Inter Miami CF",
                away_team="Orlando City SC",
                match_datetime=datetime.now() + timedelta(days=1),
            ),
        ]
        u15_matches = [
            Match(
                match_id="2",
                home_team="Inter Miami CF",
                away_team="Tampa Bay United",
                match_datetime=datetime.now() + timedelta(days=2),
            ),
        ]

        call_count = 0

        async def mock_scrape(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return u14_matches
            return u15_matches

        with patch("src.scraper.division_discovery.MLSScraper") as mock_scraper_cls:
            mock_scraper = AsyncMock()
            mock_scraper.scrape_matches.side_effect = mock_scrape
            mock_scraper_cls.return_value = mock_scraper

            clubs = await discoverer.discover()

        assert len(clubs) == 3
        # Inter Miami appears in both U14 and U15
        inter_miami = next(c for c in clubs if c.club_name == "Inter Miami CF")
        assert set(inter_miami.teams[0].age_groups) == {"U14", "U15"}
        # Orlando only in U14
        orlando = next(c for c in clubs if c.club_name == "Orlando City SC")
        assert orlando.teams[0].age_groups == ["U14"]
        # Tampa Bay only in U15
        tampa = next(c for c in clubs if c.club_name == "Tampa Bay United")
        assert tampa.teams[0].age_groups == ["U15"]


class TestDiscoverCLI:
    """Test the discover CLI command."""

    def setup_method(self):
        from typer.testing import CliRunner

        self.runner = CliRunner(env={"NO_COLOR": "1"})

    def test_discover_invalid_division(self):
        from src.cli.main import app

        result = self.runner.invoke(app, ["discover", "--division", "InvalidDiv"])
        assert result.exit_code == 1
        assert "Invalid division" in result.output

    def test_discover_invalid_league(self):
        from src.cli.main import app

        result = self.runner.invoke(
            app, ["discover", "--division", "Florida", "--league", "BadLeague"]
        )
        assert result.exit_code == 1
        assert "Invalid league" in result.output

    def test_discover_invalid_age_group(self):
        from src.cli.main import app

        result = self.runner.invoke(
            app, ["discover", "--division", "Florida", "--age-groups", "U99"]
        )
        assert result.exit_code == 1
        assert "Invalid age group" in result.output

    def test_discover_no_teams_found(self):
        """Test discover command when no teams are found."""
        from src.cli.main import app

        with patch(
            "src.scraper.division_discovery.DivisionDiscoverer"
        ) as mock_discoverer_cls:
            mock_discoverer = mock_discoverer_cls.return_value
            mock_discoverer.discover = AsyncMock(return_value=[])

            result = self.runner.invoke(
                app,
                ["discover", "--division", "Florida", "--age-groups", "U14"],
            )
            assert result.exit_code == 0
            assert "No teams found" in result.output

    def test_discover_success_writes_json(self):
        """Test discover command writes clubs.json-compatible output."""
        from src.cli.main import app

        mock_clubs = [
            DiscoveredClub(
                club_name="Inter Miami CF",
                teams=[
                    DiscoveredTeam(
                        team_name="Inter Miami CF",
                        league="Homegrown",
                        division="Florida",
                        age_groups=["U14"],
                    )
                ],
            ),
            DiscoveredClub(
                club_name="Orlando City SC",
                teams=[
                    DiscoveredTeam(
                        team_name="Orlando City SC",
                        league="Homegrown",
                        division="Florida",
                        age_groups=["U14", "U15"],
                    )
                ],
            ),
        ]

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            output_path = f.name

        try:
            with patch(
                "src.scraper.division_discovery.DivisionDiscoverer"
            ) as mock_discoverer_cls:
                mock_discoverer = mock_discoverer_cls.return_value
                mock_discoverer.discover = AsyncMock(return_value=mock_clubs)

                result = self.runner.invoke(
                    app,
                    [
                        "discover",
                        "--division",
                        "Florida",
                        "--age-groups",
                        "U14",
                        "--output",
                        output_path,
                    ],
                )
                assert result.exit_code == 0
                assert "Saved to" in result.output
                assert "Inter Miami CF" in result.output
                assert "Orlando City SC" in result.output

                # Verify JSON file contents
                with open(output_path) as fh:
                    data = json.load(fh)
                assert len(data) == 2
                assert data[0]["club_name"] == "Inter Miami CF"
                assert data[1]["club_name"] == "Orlando City SC"
                assert data[1]["teams"][0]["age_groups"] == ["U14", "U15"]
        finally:
            os.unlink(output_path)

    def test_discover_default_output_filename(self):
        """Test that default output filename is division-clubs.json."""
        from src.cli.main import app

        mock_clubs = [
            DiscoveredClub(
                club_name="Test FC",
                teams=[
                    DiscoveredTeam(
                        team_name="Test FC",
                        division="Florida",
                        age_groups=["U14"],
                    )
                ],
            ),
        ]

        with patch(
            "src.scraper.division_discovery.DivisionDiscoverer"
        ) as mock_discoverer_cls:
            mock_discoverer = mock_discoverer_cls.return_value
            mock_discoverer.discover = AsyncMock(return_value=mock_clubs)

            result = self.runner.invoke(
                app,
                ["discover", "--division", "Florida", "--age-groups", "U14"],
            )
            assert result.exit_code == 0
            assert "florida-clubs.json" in result.output

            # Clean up the default output file
            if os.path.exists("florida-clubs.json"):
                os.unlink("florida-clubs.json")
