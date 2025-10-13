"""Missing-table API integration for MLS Match Scraper.

Handles converting scraped match data to the missing-table API format
and posting matches to the API with proper team and entity management.
"""

import time
from datetime import datetime
from typing import Any, Optional, cast

from src.api.missing_table_client import MissingTableClient
from src.scraper.models import Match
from src.utils.logger import get_logger

logger = get_logger()


class MatchAPIIntegrator:
    """Handles integration between scraped matches and missing-table API."""

    def __init__(
        self, api_client: MissingTableClient, config: Optional[Any] = None
    ) -> None:
        """Initialize the integrator with an API client."""
        self.client = api_client
        self.config = config
        self._team_cache: dict[str, int] = {}  # team_name -> team_id
        self._age_group_cache: dict[str, int] = {}  # age_group -> id
        self._division_cache: dict[str, int] = {}  # division -> id

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

    async def preload_teams_cache(self) -> dict[str, Any]:
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

    def get_cache_stats(self) -> dict[str, Any]:
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
        self, matches: list[Match], age_group: str, division: str
    ) -> dict[str, Any]:
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
                ) from e
            else:
                raise Exception(
                    f"Failed to initialize API data for teams: {', '.join(sorted(team_names)[:3])}{'...' if len(team_names) > 3 else ''}. Error: {e}"
                ) from e

        # Load existing matches for deduplication
        existing_matches_map = await self._load_existing_matches_for_deduplication(
            matches, age_group, division
        )

        results: dict[str, Any] = {
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
                match_data = await self._convert_match_to_api_format(
                    match, age_group, division
                )

                if not match_data:
                    logger.warning(
                        f"Skipping match {match.match_id} - could not convert to API format"
                    )
                    results["skipped"] += 1
                    continue

                # Check for duplicates
                duplicate_key = self._create_match_duplicate_key(match_data)
                if duplicate_key in existing_matches_map:
                    existing_match = existing_matches_map[duplicate_key]

                    # Check if we need to update the score
                    scraped_has_score = match.has_score()
                    existing_home_score = existing_match.get("home_score")
                    existing_away_score = existing_match.get("away_score")
                    existing_has_score = (
                        existing_home_score is not None
                        and existing_away_score is not None
                        and (existing_home_score > 0 or existing_away_score > 0)
                    )

                    # If scraped match has a score and existing match doesn't, update it
                    if scraped_has_score and not existing_has_score:
                        try:
                            match_id = existing_match.get("id")
                            score_data = {
                                "home_score": match_data["home_score"],
                                "away_score": match_data["away_score"],
                                "match_status": match_data["match_status"],
                            }

                            await self.client.update_match_score(match_id, score_data)

                            logger.info(
                                f"Updated score for existing match {match.match_id}",
                                extra={
                                    "match_id": match.match_id,
                                    "existing_match_id": match_id,
                                    "home_score": score_data["home_score"],
                                    "away_score": score_data["away_score"],
                                },
                            )

                            results["updated"] += 1
                            results["updated_matches"].append(
                                {
                                    "match_id": match.match_id,
                                    "existing_match_id": match_id,
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
                                extra={
                                    "match_id": match.match_id,
                                    "existing_match_id": match_id,
                                },
                            )
                            # Fall through to mark as duplicate

                    # Match exists and no update needed
                    logger.info(
                        f"Skipping duplicate match {match.match_id}",
                        extra={
                            "match_id": match.match_id,
                            "existing_match_id": existing_match.get("id"),
                            "home_team": match.home_team,
                            "away_team": match.away_team,
                            "match_date": match_data["match_date"],
                        },
                    )
                    results["duplicates"] += 1
                    results["duplicate_matches"].append(
                        {
                            "match_id": match.match_id,
                            "existing_match_id": existing_match.get("id"),
                            "home_team": match.home_team,
                            "away_team": match.away_team,
                            "match_date": match_data["match_date"],
                        }
                    )
                    continue

                # Post to API (only if not a duplicate)
                api_result = await self.client.create_match(match_data)
                results["posted"] += 1
                results["posted_matches"].append(
                    {
                        "match_id": match.match_id,
                        "api_match_id": api_result.get("id"),
                        "home_team": match.home_team,
                        "away_team": match.away_team,
                    }
                )

                logger.info(
                    f"Successfully posted match {match.match_id} to API",
                    extra={
                        "match_id": match.match_id,
                        "api_match_id": api_result.get("id"),
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
        self, matches: list[Match], age_group: str, division: str
    ) -> None:
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
        self, team_names: set[str], age_group: str, division: str
    ) -> None:
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
            teams_response = await self.client._make_request("GET", "api/teams")

            # Handle both array response and wrapped response
            if isinstance(teams_response, dict) and "teams" in teams_response:
                teams_list = cast(list[Any], teams_response["teams"])
            else:
                teams_list = cast(list[Any], teams_response)

            for team in teams_list:
                if team.get("name") == team_name:
                    team_id: Optional[int] = team.get("id")
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

    async def _cache_age_group_id(self, age_group: str) -> None:
        """Cache the age group ID."""
        if age_group not in self._age_group_cache:
            age_group_id = await self._get_age_group_id(age_group)
            if age_group_id:
                self._age_group_cache[age_group] = age_group_id

    async def _cache_division_id(self, division: str) -> None:
        """Cache the division ID."""
        if division not in self._division_cache:
            division_id = await self._get_division_id(division)
            if division_id:
                self._division_cache[division] = division_id

    async def _get_age_group_id(self, age_group: str) -> Optional[int]:
        """Get age group ID from the API."""
        try:
            age_groups_response = await self.client._make_request(
                "GET", "api/age-groups"
            )

            # Handle both array response and wrapped response
            if (
                isinstance(age_groups_response, dict)
                and "age_groups" in age_groups_response
            ):
                age_groups_list = cast(list[Any], age_groups_response["age_groups"])
            else:
                age_groups_list = cast(list[Any], age_groups_response)

            for ag in age_groups_list:
                if ag.get("name") == age_group:
                    age_group_id: Optional[int] = ag.get("id")
                    return age_group_id

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
            divisions_response = await self.client._make_request("GET", "api/divisions")

            # Handle both array response and wrapped response
            if (
                isinstance(divisions_response, dict)
                and "divisions" in divisions_response
            ):
                divisions_list = cast(list[Any], divisions_response["divisions"])
            else:
                divisions_list = cast(list[Any], divisions_response)

            for div in divisions_list:
                if div.get("name") == division:
                    division_id: Optional[int] = div.get("id")
                    return division_id

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
            seasons_response = await self.client._make_request("GET", "api/seasons")

            # Handle both array response and wrapped response
            if isinstance(seasons_response, dict) and "seasons" in seasons_response:
                seasons_list = cast(list[Any], seasons_response["seasons"])
            else:
                seasons_list = cast(list[Any], seasons_response)

            # Find the most recent season that covers the current date
            current_date = datetime.now().date()
            current_year = current_date.year

            for season in seasons_list:
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
                                season_id: int = season.get("id")
                                return season_id
                        except Exception:
                            pass  # If date parsing fails, just use year matching

                    # If no date range or parsing failed, use this season
                    season_id_fallback: int = season.get("id")
                    return season_id_fallback

            # If no season found, return the first available one
            if seasons_list:
                first_season_id: int = seasons_list[0].get("id")
                return first_season_id

            return 1  # Default fallback

        except Exception as e:
            logger.warning(f"Error getting season: {e}")
            return 1  # Default fallback

    async def _get_match_type_id(self) -> int:
        """Get match type ID for regular league matches."""
        try:
            match_types_response = await self.client._make_request(
                "GET", "api/match-types"
            )

            # Handle both array response and wrapped response
            if (
                isinstance(match_types_response, dict)
                and "match_types" in match_types_response
            ):
                match_types_list = cast(list[Any], match_types_response["match_types"])
            else:
                match_types_list = cast(list[Any], match_types_response)

            # Look for "League" or "Regular" match type
            for mt in match_types_list:
                name = mt.get("name", "").lower()
                if "league" in name or "regular" in name:
                    match_type_id: int = mt.get("id")
                    return match_type_id

            # Return first available or default
            if match_types_list:
                first_match_type_id: int = match_types_list[0].get("id")
                return first_match_type_id

            return 1  # Default fallback

        except Exception as e:
            logger.warning(f"Error getting match type: {e}")
            return 1  # Default fallback

    async def _convert_match_to_api_format(
        self, match: Match, age_group: str, division: str
    ) -> Optional[dict]:
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
            match_type_id = await self._get_match_type_id()

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
            match_date = match.match_datetime.date().isoformat()

            api_data = {
                "match_id": match.match_id,
                "match_date": match_date,
                "home_team_id": home_team_id,
                "away_team_id": away_team_id,
                "home_score": home_score,
                "away_score": away_score,
                "match_status": match.match_status,
                "season_id": season_id,
                "age_group_id": age_group_id,
                "match_type_id": match_type_id,
                "division_id": division_id,
            }

            return api_data

        except Exception as e:
            logger.error(f"Error converting match {match.match_id} to API format: {e}")
            return None

    async def _load_existing_matches_for_deduplication(
        self, matches: list[Match], age_group: str, division: str
    ) -> dict[str, dict]:
        """
        Load existing matches from API for deduplication checking.

        Args:
            matches: List of matches being processed
            age_group: Age group filter
            division: Division filter

        Returns:
            Dictionary mapping duplicate keys to existing match data
        """
        try:
            logger.info("Loading existing matches for deduplication")

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

            # Query existing matches with filters
            filters: dict[str, Any] = {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            }

            # Add ID filters if available
            if age_group_id:
                filters["age_group_id"] = age_group_id
            if division_id:
                filters["division_id"] = division_id

            existing_matches = await self.client.list_matches(**filters)

            # Build duplicate key map
            existing_matches_map = {}
            for match in existing_matches:
                duplicate_key = self._create_match_duplicate_key(match)
                existing_matches_map[duplicate_key] = match

            logger.info(
                f"Loaded {len(existing_matches)} existing matches for deduplication",
                extra={
                    "date_range": f"{start_date} to {end_date}",
                    "existing_matches_count": len(existing_matches),
                },
            )

            return existing_matches_map

        except Exception as e:
            logger.warning(f"Failed to load existing matches for deduplication: {e}")
            # Continue without deduplication rather than failing completely
            return {}

    def _create_match_duplicate_key(self, match_data: dict[str, Any]) -> str:
        """
        Create a unique key for match deduplication.

        Args:
            match_data: Match data dictionary

        Returns:
            Unique key string for the match
        """
        # Use match_date + home_team_id + away_team_id as unique identifier
        match_date = match_data.get("match_date", "")
        home_team_id = match_data.get("home_team_id", "")
        away_team_id = match_data.get("away_team_id", "")

        return f"{match_date}:{home_team_id}:{away_team_id}"

    async def post_matches_async(
        self, matches: list[Match], age_group: str, division: str
    ) -> dict[str, Any]:
        """
        Post matches using async API endpoint (via Celery workers).

        This method submits matches to /api/matches/submit which queues them
        for async processing. It's faster for bulk operations and doesn't require
        preloading team caches or entity IDs.

        Args:
            matches: List of Match objects to post
            age_group: Age group (e.g., "U14")
            division: Division (e.g., "Northeast")

        Returns:
            Dictionary with posting results and task IDs
        """
        if not matches:
            logger.info("No matches to post to API")
            return {"posted": 0, "errors": 0, "task_ids": []}

        logger.info(
            f"Starting async API integration for {len(matches)} matches",
            extra={
                "match_count": len(matches),
                "age_group": age_group,
                "division": division,
            },
        )

        results: dict[str, Any] = {
            "posted": 0,
            "errors": 0,
            "task_ids": [],
            "failed_matches": [],
            "posted_matches": [],
        }

        for match in matches:
            try:
                # Convert match to async API format (uses team names, not IDs)
                match_data = self._convert_match_to_async_format(
                    match, age_group, division
                )

                if not match_data:
                    logger.warning(
                        f"Skipping match {match.match_id} - could not convert to async format"
                    )
                    results["errors"] += 1
                    continue

                # Submit to async API
                submit_result = await self.client.submit_match_async(match_data)
                task_id = submit_result.get("task_id")

                results["posted"] += 1
                results["task_ids"].append(task_id)
                results["posted_matches"].append(
                    {
                        "match_id": match.match_id,
                        "task_id": task_id,
                        "home_team": match.home_team,
                        "away_team": match.away_team,
                    }
                )

                logger.info(
                    f"Successfully submitted match {match.match_id} for async processing",
                    extra={
                        "match_id": match.match_id,
                        "task_id": task_id,
                        "home_team": match.home_team,
                        "away_team": match.away_team,
                    },
                )

            except Exception as e:
                logger.error(
                    f"Failed to submit match {match.match_id} to async API: {e}",
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
            "Async API integration completed",
            extra={
                "posted": results["posted"],
                "errors": results["errors"],
                "task_count": len(results["task_ids"]),
            },
        )

        return results

    def _convert_match_to_async_format(
        self, match: Match, age_group: str, division: str
    ) -> Optional[dict]:
        """
        Convert a Match object to async API format (with team names).

        The async API accepts team names instead of IDs and handles
        entity resolution on the backend via Celery workers.

        Args:
            match: Match object to convert
            age_group: Age group name
            division: Division name

        Returns:
            Dictionary for async API submission or None if conversion fails
        """
        try:
            # Use normalized team names
            home_team = self._normalize_team_name(match.home_team)
            away_team = self._normalize_team_name(match.away_team)

            # Handle scores
            home_score = None
            away_score = None

            if match.home_score is not None and str(match.home_score).isdigit():
                home_score = int(match.home_score)
            if match.away_score is not None and str(match.away_score).isdigit():
                away_score = int(match.away_score)

            # Format match date as ISO string
            match_date = match.match_datetime.isoformat()

            # Determine season from match date (simple logic - could be enhanced)
            match_year = match.match_datetime.year
            match_month = match.match_datetime.month

            # MLS Next season typically runs Aug-July
            if match_month >= 8:  # August or later
                season = f"{match_year}-{str(match_year + 1)[2:]}"
            else:
                season = f"{match_year - 1}-{str(match_year)[2:]}"

            api_data = {
                "home_team": home_team,
                "away_team": away_team,
                "match_date": match_date,
                "season": season,
                "age_group": age_group,
                "division": division,
                "match_status": match.match_status,
                "match_type": "League",  # Default to League
                "location": None,  # Not available from MLS scraping
                "external_match_id": match.match_id,  # Use scraped ID for deduplication
            }

            # Add scores if available
            if home_score is not None:
                api_data["home_score"] = home_score
            if away_score is not None:
                api_data["away_score"] = away_score

            return api_data

        except Exception as e:
            logger.error(
                f"Error converting match {match.match_id} to async format: {e}"
            )
            return None
