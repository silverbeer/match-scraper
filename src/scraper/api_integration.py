"""Missing-table API integration for MLS Match Scraper.

Handles converting scraped match data to the missing-table API format
and posting matches to the API with proper team and entity management.
"""

import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from src.api.missing_table_client import MissingTableClient
from src.scraper.models import Match
from src.utils.logger import get_logger

logger = get_logger()


class MatchAPIIntegrator:
    """Handles integration between scraped matches and missing-table API."""

    def __init__(self, api_client: MissingTableClient, config=None):
        """Initialize the integrator with an API client."""
        self.client = api_client
        self.config = config
        self._team_cache: Dict[str, int] = {}  # team_name -> team_id
        self._age_group_cache: Dict[str, int] = {}  # age_group -> id
        self._division_cache: Dict[str, int] = {}  # division -> id

        # New bulk cache system
        self._teams_cache_loaded: bool = False
        self._cache_load_time: Optional[float] = None
        self._cache_hit_count: int = 0
        self._cache_miss_count: int = 0

        # Team name mappings for normalization
        self._team_name_mappings = {
            "Intercontinental Football Academy of New England": "IFA",
        }

    def _normalize_team_name(self, team_name: str) -> str:
        """Normalize team names using predefined mappings."""
        return self._team_name_mappings.get(team_name, team_name)

    async def preload_teams_cache(self) -> Dict[str, any]:
        """
        Bulk load all teams from the API and build the cache.

        Returns:
            Dictionary with cache loading statistics
        """
        if self._teams_cache_loaded:
            return {
                "already_loaded": True,
                "cache_size": len(self._team_cache),
                "load_time": self._cache_load_time,
            }

        start_time = time.time()
        logger.info("Starting bulk team cache preload")

        try:
            # Bulk load all teams from API
            teams_response = await self.client._make_request("GET", "api/teams")

            # Handle both array and wrapped response formats
            if isinstance(teams_response, dict) and "teams" in teams_response:
                teams = teams_response["teams"]
            else:
                teams = teams_response

            # Build the cache
            team_count = 0
            for team in teams:
                if isinstance(team, dict) and "name" in team and "id" in team:
                    normalized_name = self._normalize_team_name(team["name"])
                    self._team_cache[normalized_name] = team["id"]
                    team_count += 1

            self._teams_cache_loaded = True
            self._cache_load_time = time.time() - start_time

            logger.info(
                f"Successfully loaded {team_count} teams into cache",
                extra={"team_count": team_count, "load_time": self._cache_load_time},
            )

            return {
                "success": True,
                "team_count": team_count,
                "load_time": self._cache_load_time,
                "cache_size": len(self._team_cache),
            }

        except Exception as e:
            logger.error(f"Failed to preload teams cache: {e}")
            return {
                "success": False,
                "error": str(e),
                "load_time": time.time() - start_time,
            }

    def get_cache_stats(self) -> Dict[str, any]:
        """Get current cache statistics."""
        return {
            "loaded": self._teams_cache_loaded,
            "team_count": len(self._team_cache),
            "load_time": self._cache_load_time,
            "hit_count": self._cache_hit_count,
            "miss_count": self._cache_miss_count,
            "hit_rate": self._cache_hit_count
            / max(1, self._cache_hit_count + self._cache_miss_count),
        }

    def clear_cache(self) -> None:
        """Clear the teams cache for testing purposes."""
        self._team_cache.clear()
        self._teams_cache_loaded = False
        self._cache_load_time = None
        self._cache_hit_count = 0
        self._cache_miss_count = 0
        logger.info("Teams cache cleared")

    async def post_matches(
        self, matches: List[Match], age_group: str, division: str
    ) -> Dict[str, any]:
        """
        Post a list of matches to the missing-table API.

        Args:
            matches: List of Match objects to post
            age_group: Age group (e.g., "U14")
            division: Division (e.g., "Northeast")

        Returns:
            Dictionary with posting results and statistics
        """
        if not matches:
            logger.info("No matches to post to API")
            return {"posted": 0, "errors": 0, "skipped": 0}

        logger.info(
            f"Starting API integration for {len(matches)} matches",
            extra={
                "match_count": len(matches),
                "age_group": age_group,
                "division": division,
            },
        )

        # Initialize entity IDs (preload cache first if enabled)
        try:
            # Preload teams cache for better performance if enabled
            if self.config and self.config.enable_team_cache:
                cache_result = await self.preload_teams_cache()
                if not cache_result.get(
                    "success", True
                ):  # True for already_loaded case
                    error_msg = cache_result.get("error", "Unknown cache preload error")
                    logger.error(f"Teams cache preload failed: {error_msg}")
                    raise RuntimeError(f"Cache preload failed: {error_msg}")

            await self._initialize_entity_ids(matches, age_group, division)
        except Exception as e:
            # Extract team names for better error context
            team_names = set()
            for match in matches:
                team_names.add(self._normalize_team_name(match.home_team))
                team_names.add(self._normalize_team_name(match.away_team))

            # Check if it's a network connectivity issue
            error_str = str(e).lower()
            if "nodename nor servname" in error_str or "connection" in error_str:
                raise Exception(
                    f"Cannot connect to missing-table API server. Please check your network connection or API configuration. Teams involved: {', '.join(sorted(team_names)[:3])}{'...' if len(team_names) > 3 else ''}"
                )
            else:
                raise Exception(
                    f"Failed to initialize API data for teams: {', '.join(sorted(team_names)[:3])}{'...' if len(team_names) > 3 else ''}. Error: {e}"
                )

        # Load existing games for deduplication
        existing_games_map = await self._load_existing_games_for_deduplication(
            matches, age_group, division
        )

        results = {
            "posted": 0,
            "errors": 0,
            "skipped": 0,
            "duplicates": 0,
            "updated": 0,
            "failed_matches": [],
            "posted_matches": [],
            "duplicate_matches": [],
            "updated_matches": [],
        }

        for match in matches:
            try:
                # Convert match to API format
                game_data = await self._convert_match_to_api_format(
                    match, age_group, division
                )

                if not game_data:
                    logger.warning(
                        f"Skipping match {match.match_id} - could not convert to API format"
                    )
                    results["skipped"] += 1
                    continue

                # Check for duplicates
                duplicate_key = self._create_game_duplicate_key(game_data)
                if duplicate_key in existing_games_map:
                    existing_game = existing_games_map[duplicate_key]

                    # Check if we need to update the score
                    scraped_has_score = match.has_score()
                    existing_home_score = existing_game.get("home_score")
                    existing_away_score = existing_game.get("away_score")
                    existing_has_score = (
                        existing_home_score is not None
                        and existing_away_score is not None
                        and (existing_home_score > 0 or existing_away_score > 0)
                    )

                    # If scraped match has a score and existing game doesn't, update it
                    if scraped_has_score and not existing_has_score:
                        try:
                            game_id = existing_game.get("id")
                            score_data = {
                                "home_score": game_data["home_score"],
                                "away_score": game_data["away_score"],
                                "match_status": game_data["match_status"],
                            }

                            await self.client.update_score(game_id, score_data)

                            logger.info(
                                f"Updated score for existing match {match.match_id}",
                                extra={
                                    "match_id": match.match_id,
                                    "existing_game_id": game_id,
                                    "home_score": score_data["home_score"],
                                    "away_score": score_data["away_score"],
                                },
                            )

                            results["updated"] += 1
                            results["updated_matches"].append(
                                {
                                    "match_id": match.match_id,
                                    "existing_game_id": game_id,
                                    "home_team": match.home_team,
                                    "away_team": match.away_team,
                                    "home_score": score_data["home_score"],
                                    "away_score": score_data["away_score"],
                                }
                            )
                            continue

                        except Exception as e:
                            logger.error(
                                f"Failed to update score for match {match.match_id}: {e}",
                                extra={"match_id": match.match_id, "game_id": game_id},
                            )
                            # Fall through to mark as duplicate

                    # Game exists and no update needed
                    logger.info(
                        f"Skipping duplicate match {match.match_id}",
                        extra={
                            "match_id": match.match_id,
                            "existing_game_id": existing_game.get("id"),
                            "home_team": match.home_team,
                            "away_team": match.away_team,
                            "game_date": game_data["game_date"],
                        },
                    )
                    results["duplicates"] += 1
                    results["duplicate_matches"].append(
                        {
                            "match_id": match.match_id,
                            "existing_game_id": existing_game.get("id"),
                            "home_team": match.home_team,
                            "away_team": match.away_team,
                            "game_date": game_data["game_date"],
                        }
                    )
                    continue

                # Post to API (only if not a duplicate)
                api_result = await self.client.create_game(game_data)
                results["posted"] += 1
                results["posted_matches"].append(
                    {
                        "match_id": match.match_id,
                        "api_game_id": api_result.get("id"),
                        "home_team": match.home_team,
                        "away_team": match.away_team,
                    }
                )

                logger.info(
                    f"Successfully posted match {match.match_id} to API",
                    extra={
                        "match_id": match.match_id,
                        "api_game_id": api_result.get("id"),
                        "home_team": match.home_team,
                        "away_team": match.away_team,
                    },
                )

            except Exception as e:
                logger.error(
                    f"Failed to post match {match.match_id} to API: {e}",
                    extra={"match_id": match.match_id, "error": str(e)},
                )
                results["errors"] += 1
                results["failed_matches"].append(
                    {
                        "match_id": match.match_id,
                        "error": str(e),
                        "home_team": match.home_team,
                        "away_team": match.away_team,
                    }
                )

        logger.info(
            "API integration completed",
            extra={
                "posted": results["posted"],
                "errors": results["errors"],
                "skipped": results["skipped"],
            },
        )

        return results

    async def _initialize_entity_ids(
        self, matches: List[Match], age_group: str, division: str
    ):
        """Initialize and cache entity IDs needed for API calls."""
        logger.info("Initializing entity IDs for API integration")

        # Extract unique team names and normalize them
        team_names = set()
        for match in matches:
            team_names.add(self._normalize_team_name(match.home_team))
            team_names.add(self._normalize_team_name(match.away_team))

        # Get or create teams
        await self._ensure_teams_exist(team_names, age_group, division)

        # Cache age group and division IDs
        await self._cache_age_group_id(age_group)
        await self._cache_division_id(division)

    async def _ensure_teams_exist(
        self, team_names: Set[str], age_group: str, division: str
    ):
        """Ensure all teams exist in the API and cache their IDs."""
        logger.info(f"Ensuring {len(team_names)} teams exist in API")

        for team_name in team_names:
            if team_name in self._team_cache:
                continue

            try:
                # Try to find existing team first
                team_id = await self._find_team_by_name(team_name)

                if team_id:
                    self._team_cache[team_name] = team_id
                    logger.info(f"Found existing team: {team_name} (ID: {team_id})")
                else:
                    # Create new team
                    team_id = await self._create_team(team_name, age_group, division)
                    self._team_cache[team_name] = team_id
                    logger.info(f"Created new team: {team_name} (ID: {team_id})")

            except Exception as e:
                logger.error(f"Failed to ensure team exists: {team_name} - {e}")
                raise RuntimeError(
                    f"Team creation/lookup failed for '{team_name}': {e}"
                ) from e

    async def _find_team_by_name(self, team_name: str) -> Optional[int]:
        """Find a team by name using cache or API fallback."""
        normalized_name = self._normalize_team_name(team_name)

        # Try cache first if it's loaded and enabled
        if self._teams_cache_loaded and (
            not self.config or self.config.enable_team_cache
        ):
            if normalized_name in self._team_cache:
                self._cache_hit_count += 1
                return self._team_cache[normalized_name]
            else:
                self._cache_miss_count += 1
                # Cache miss - team might be newly created, refresh cache if enabled
                if not self.config or self.config.cache_refresh_on_miss:
                    logger.info(f"Cache miss for team '{team_name}', refreshing cache")
                    await self._refresh_single_team_in_cache(normalized_name)
                    if normalized_name in self._team_cache:
                        return self._team_cache[normalized_name]

        # Fallback to original API lookup if cache not available
        try:
            teams = await self.client._make_request("GET", "api/teams")

            # Handle both array response and wrapped response
            if isinstance(teams, dict) and "teams" in teams:
                teams = teams["teams"]

            for team in teams:
                if team.get("name") == team_name:
                    team_id = team.get("id")
                    # Update cache if available
                    if self._teams_cache_loaded:
                        self._team_cache[normalized_name] = team_id
                    return team_id

            return None

        except Exception as e:
            logger.warning(f"Error searching for team {team_name}: {e}")
            return None

    async def _refresh_single_team_in_cache(self, team_name: str) -> None:
        """Refresh a single team in the cache by fetching updated data."""
        try:
            teams = await self.client._make_request("GET", "api/teams")

            if isinstance(teams, dict) and "teams" in teams:
                teams = teams["teams"]

            for team in teams:
                if isinstance(team, dict) and "name" in team and "id" in team:
                    normalized_name = self._normalize_team_name(team["name"])
                    if normalized_name == team_name or team["name"] == team_name:
                        self._team_cache[normalized_name] = team["id"]
                        logger.info(f"Updated cache for team: {team_name}")
                        return

        except Exception as e:
            logger.warning(f"Failed to refresh team cache for {team_name}: {e}")

    async def _create_team(self, team_name: str, age_group: str, division: str) -> int:
        """Create a new team in the API."""
        # Get age group and division IDs first
        age_group_id = await self._get_age_group_id(age_group)
        division_id = await self._get_division_id(division)

        team_data = {
            "name": team_name,
            "city": "Unknown",  # We don't have city info from scraping
            "age_group_ids": [age_group_id] if age_group_id else [],
            "division_ids": [division_id] if division_id else [],
            "academy_team": False,
        }

        response = await self.client._make_request("POST", "api/teams", data=team_data)
        team_id = response.get("id")

        # Add newly created team to cache
        if self._teams_cache_loaded and team_id:
            normalized_name = self._normalize_team_name(team_name)
            self._team_cache[normalized_name] = team_id
            logger.info(
                f"Added newly created team to cache: {team_name} (ID: {team_id})"
            )

        return team_id

    async def _cache_age_group_id(self, age_group: str):
        """Cache the age group ID."""
        if age_group not in self._age_group_cache:
            age_group_id = await self._get_age_group_id(age_group)
            if age_group_id:
                self._age_group_cache[age_group] = age_group_id

    async def _cache_division_id(self, division: str):
        """Cache the division ID."""
        if division not in self._division_cache:
            division_id = await self._get_division_id(division)
            if division_id:
                self._division_cache[division] = division_id

    async def _get_age_group_id(self, age_group: str) -> Optional[int]:
        """Get age group ID from the API."""
        try:
            age_groups = await self.client._make_request("GET", "api/age-groups")

            # Handle both array response and wrapped response
            if isinstance(age_groups, dict) and "age_groups" in age_groups:
                age_groups = age_groups["age_groups"]

            for ag in age_groups:
                if ag.get("name") == age_group:
                    return ag.get("id")

            # If not found, create it
            age_group_data = {"name": age_group}
            response = await self.client._make_request(
                "POST", "api/age-groups", data=age_group_data
            )
            return response.get("id")

        except Exception as e:
            logger.warning(f"Error getting/creating age group {age_group}: {e}")
            return None

    async def _get_division_id(self, division: str) -> Optional[int]:
        """Get division ID from the API."""
        try:
            divisions = await self.client._make_request("GET", "api/divisions")

            # Handle both array response and wrapped response
            if isinstance(divisions, dict) and "divisions" in divisions:
                divisions = divisions["divisions"]

            for div in divisions:
                if div.get("name") == division:
                    return div.get("id")

            # If not found, create it
            division_data = {"name": division}
            response = await self.client._make_request(
                "POST", "api/divisions", data=division_data
            )
            return response.get("id")

        except Exception as e:
            logger.warning(f"Error getting/creating division {division}: {e}")
            return None

    async def _get_season_id(self) -> int:
        """Get current season ID."""
        try:
            seasons = await self.client._make_request("GET", "api/seasons")

            # Handle both array response and wrapped response
            if isinstance(seasons, dict) and "seasons" in seasons:
                seasons = seasons["seasons"]

            # Find the most recent season that covers the current date
            current_date = datetime.now().date()
            current_year = current_date.year

            for season in seasons:
                # Check if season name contains current year or next year
                season_name = season.get("name", "")
                if (
                    str(current_year) in season_name
                    or str(current_year + 1) in season_name
                ):
                    # Additional check: if we have start/end dates, verify current date is in range
                    start_date_str = season.get("start_date")
                    end_date_str = season.get("end_date")

                    if start_date_str and end_date_str:
                        try:
                            start_date = datetime.fromisoformat(start_date_str).date()
                            end_date = datetime.fromisoformat(end_date_str).date()
                            if start_date <= current_date <= end_date:
                                return season.get("id")
                        except:
                            pass  # If date parsing fails, just use year matching

                    # If no date range or parsing failed, use this season
                    return season.get("id")

            # If no season found, return the first available one
            if seasons:
                return seasons[0].get("id")

            return 1  # Default fallback

        except Exception as e:
            logger.warning(f"Error getting season: {e}")
            return 1  # Default fallback

    async def _get_game_type_id(self) -> int:
        """Get game type ID for regular league games."""
        try:
            game_types = await self.client._make_request("GET", "api/game-types")

            # Handle both array response and wrapped response
            if isinstance(game_types, dict) and "game_types" in game_types:
                game_types = game_types["game_types"]

            # Look for "League" or "Regular" game type
            for gt in game_types:
                name = gt.get("name", "").lower()
                if "league" in name or "regular" in name:
                    return gt.get("id")

            # Return first available or default
            if game_types:
                return game_types[0].get("id")

            return 1  # Default fallback

        except Exception as e:
            logger.warning(f"Error getting game type: {e}")
            return 1  # Default fallback

    async def _convert_match_to_api_format(
        self, match: Match, age_group: str, division: str
    ) -> Optional[Dict]:
        """Convert a Match object to the API format."""
        try:
            # Get team IDs using normalized team names
            normalized_home_team = self._normalize_team_name(match.home_team)
            normalized_away_team = self._normalize_team_name(match.away_team)
            home_team_id = self._team_cache.get(normalized_home_team)
            away_team_id = self._team_cache.get(normalized_away_team)

            if not home_team_id or not away_team_id:
                logger.warning(f"Missing team IDs for match {match.match_id}")
                return None

            # Get entity IDs
            age_group_id = self._age_group_cache.get(age_group)
            division_id = self._division_cache.get(division)
            season_id = await self._get_season_id()
            game_type_id = await self._get_game_type_id()

            if not age_group_id:
                logger.warning(f"Missing age group ID for {age_group}")
                return None

            # Handle scores - API expects integers
            home_score = 0
            away_score = 0

            if match.home_score is not None and str(match.home_score).isdigit():
                home_score = int(match.home_score)
            if match.away_score is not None and str(match.away_score).isdigit():
                away_score = int(match.away_score)

            # Format date for API (API expects just date, not datetime)
            game_date = match.match_datetime.date().isoformat()

            api_data = {
                "match_id": match.match_id,
                "game_date": game_date,
                "home_team_id": home_team_id,
                "away_team_id": away_team_id,
                "home_score": home_score,
                "away_score": away_score,
                "match_status": match.match_status,
                "season_id": season_id,
                "age_group_id": age_group_id,
                "game_type_id": game_type_id,
                "division_id": division_id,
            }

            return api_data

        except Exception as e:
            logger.error(f"Error converting match {match.match_id} to API format: {e}")
            return None

    async def _load_existing_games_for_deduplication(
        self, matches: List[Match], age_group: str, division: str
    ) -> Dict[str, Dict]:
        """
        Load existing games from API for deduplication checking.

        Args:
            matches: List of matches being processed
            age_group: Age group filter
            division: Division filter

        Returns:
            Dictionary mapping duplicate keys to existing game data
        """
        try:
            logger.info("Loading existing games for deduplication")

            # Get date range from matches
            dates = [
                match.match_datetime.date() for match in matches if match.match_datetime
            ]
            if not dates:
                logger.warning("No valid dates found in matches for deduplication")
                return {}

            start_date = min(dates)
            end_date = max(dates)

            # Get age group and division IDs for filtering
            age_group_id = self._age_group_cache.get(age_group)
            division_id = self._division_cache.get(division)

            # Query existing games with filters
            filters = {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            }

            # Add ID filters if available
            if age_group_id:
                filters["age_group_id"] = age_group_id
            if division_id:
                filters["division_id"] = division_id

            existing_games = await self.client.list_games(**filters)

            # Build duplicate key map
            existing_games_map = {}
            for game in existing_games:
                duplicate_key = self._create_game_duplicate_key(game)
                existing_games_map[duplicate_key] = game

            logger.info(
                f"Loaded {len(existing_games)} existing games for deduplication",
                extra={
                    "date_range": f"{start_date} to {end_date}",
                    "existing_games_count": len(existing_games),
                },
            )

            return existing_games_map

        except Exception as e:
            logger.warning(f"Failed to load existing games for deduplication: {e}")
            # Continue without deduplication rather than failing completely
            return {}

    def _create_game_duplicate_key(self, game_data: Dict[str, Any]) -> str:
        """
        Create a unique key for game deduplication.

        Args:
            game_data: Game data dictionary

        Returns:
            Unique key string for the game
        """
        # Use game_date + home_team_id + away_team_id as unique identifier
        game_date = game_data.get("game_date", "")
        home_team_id = game_data.get("home_team_id", "")
        away_team_id = game_data.get("away_team_id", "")

        return f"{game_date}:{home_team_id}:{away_team_id}"
