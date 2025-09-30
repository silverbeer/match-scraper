"""
MissingTable.com API client for match data integration.

This module provides a client for communicating with the missing-table.com API
to create games, update scores, and manage match data with proper authentication,
error handling, and retry logic.
"""

import asyncio
import os
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import httpx
from pydantic import BaseModel

from ..utils.logger import get_logger

logger = get_logger()


class HealthStatus(BaseModel):
    """Health check response model."""
    status: str
    version: Optional[str] = None
    database: Optional[str] = None
    timestamp: Optional[str] = None


class MissingTableAPIError(Exception):
    """Base exception for MissingTable API errors."""

    def __init__(self, message: str, status_code: Optional[int] = None, response_data: Optional[Dict] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data


class MissingTableClient:
    """
    Client for interacting with the missing-table.com API.

    Provides methods for health checks, game creation, score updates,
    with built-in authentication, retry logic, and comprehensive error handling.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_token: Optional[str] = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        retry_backoff_base: float = 1.0,
    ):
        """
        Initialize the MissingTable API client.

        Args:
            base_url: Base URL for the API (defaults to environment variable)
            api_token: Bearer token for authentication (defaults to environment variable)
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
            retry_backoff_base: Base delay for exponential backoff
        """
        self.base_url = base_url or os.getenv("MISSING_TABLE_API_BASE_URL", "http://localhost:8000")
        self.api_token = api_token or os.getenv("MISSING_TABLE_API_TOKEN")
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_backoff_base = retry_backoff_base

        # Ensure base URL ends with /
        if not self.base_url.endswith("/"):
            self.base_url += "/"

        if not self.api_token:
            logger.warning("No API token provided. Set MISSING_TABLE_API_TOKEN environment variable.")

    @property
    def headers(self) -> Dict[str, str]:
        """Get request headers with authentication."""
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "match-scraper/1.0",
        }

        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"

        return headers

    async def health_check(self, full: bool = False) -> HealthStatus:
        """
        Perform a health check on the missing-table API.

        This should be the first method called to ensure the API is available.

        Args:
            full: If True, perform comprehensive health check (/health/full)
                 If False, perform basic health check (/health)

        Returns:
            HealthStatus object with API status information

        Raises:
            MissingTableAPIError: If health check fails
        """
        endpoint = "health/full" if full else "health"
        url = urljoin(self.base_url, endpoint)

        logger.info(
            "Performing health check",
            extra={
                "endpoint": endpoint,
                "url": url,
                "full_check": full,
            }
        )

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # Health check doesn't require authentication
                headers = {
                    "Content-Type": "application/json",
                    "User-Agent": "match-scraper/1.0",
                }

                response = await client.get(url, headers=headers)
                response.raise_for_status()

                health_data = response.json()
                logger.info(
                    "Health check successful",
                    extra={
                        "status_code": response.status_code,
                        "response": health_data,
                    }
                )

                return HealthStatus(**health_data)

        except httpx.HTTPStatusError as e:
            error_msg = f"Health check failed with status {e.response.status_code}"
            logger.error(
                error_msg,
                extra={
                    "status_code": e.response.status_code,
                    "response_text": e.response.text,
                }
            )
            raise MissingTableAPIError(
                error_msg,
                status_code=e.response.status_code,
                response_data=e.response.json() if e.response.content else None
            )

        except httpx.RequestError as e:
            error_msg = f"Health check request failed: {str(e)}"
            logger.error(error_msg, extra={"error": str(e)})
            raise MissingTableAPIError(error_msg)

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Make an authenticated API request with retry logic.

        Args:
            method: HTTP method (GET, POST, PUT, etc.)
            endpoint: API endpoint path
            data: Request body data
            params: Query parameters

        Returns:
            Response JSON data

        Raises:
            MissingTableAPIError: If request fails after all retries
        """
        if not self.api_token:
            raise MissingTableAPIError("API token is required for authenticated requests")

        url = urljoin(self.base_url, endpoint)

        for attempt in range(self.max_retries + 1):
            try:
                logger.debug(
                    f"Making {method} request to {endpoint}",
                    extra={
                        "attempt": attempt + 1,
                        "max_retries": self.max_retries + 1,
                        "url": url,
                        "has_data": data is not None,
                    }
                )

                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.request(
                        method=method,
                        url=url,
                        headers=self.headers,
                        json=data,
                        params=params,
                    )

                    response.raise_for_status()

                    result = response.json()
                    logger.info(
                        f"{method} request successful",
                        extra={
                            "endpoint": endpoint,
                            "status_code": response.status_code,
                            "attempt": attempt + 1,
                        }
                    )

                    return result

            except httpx.HTTPStatusError as e:
                if e.response.status_code < 500 or attempt == self.max_retries:
                    # Don't retry client errors (4xx) or if we've exhausted retries
                    error_msg = f"{method} {endpoint} failed with status {e.response.status_code}"
                    logger.error(
                        error_msg,
                        extra={
                            "status_code": e.response.status_code,
                            "response_text": e.response.text,
                            "attempt": attempt + 1,
                        }
                    )
                    raise MissingTableAPIError(
                        error_msg,
                        status_code=e.response.status_code,
                        response_data=e.response.json() if e.response.content else None
                    )

                # Server error, retry with backoff
                delay = self.retry_backoff_base * (2 ** attempt)
                logger.warning(
                    f"Server error on attempt {attempt + 1}, retrying in {delay}s",
                    extra={
                        "status_code": e.response.status_code,
                        "attempt": attempt + 1,
                        "delay": delay,
                    }
                )
                await asyncio.sleep(delay)

            except httpx.RequestError as e:
                if attempt == self.max_retries:
                    error_msg = f"{method} {endpoint} request failed: {str(e)}"
                    # Log at debug level to avoid cluttering CLI output - higher level will show user-friendly error
                    logger.debug(error_msg, extra={"error": str(e), "attempt": attempt + 1})
                    raise MissingTableAPIError(error_msg)

                # Network error, retry with backoff
                delay = self.retry_backoff_base * (2 ** attempt)
                logger.warning(
                    f"Network error on attempt {attempt + 1}, retrying in {delay}s",
                    extra={
                        "error": str(e),
                        "attempt": attempt + 1,
                        "delay": delay,
                    }
                )
                await asyncio.sleep(delay)

        # Should not reach here
        raise MissingTableAPIError(f"Request failed after {self.max_retries + 1} attempts")

    async def create_game(self, game_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new game in the missing-table API.

        Args:
            game_data: Game information dictionary

        Returns:
            Created game data from API response

        Raises:
            MissingTableAPIError: If game creation fails
        """
        logger.info(
            "Creating new game",
            extra={
                "home_team": game_data.get("home_team"),
                "away_team": game_data.get("away_team"),
                "game_date": game_data.get("game_date"),
            }
        )

        result = await self._make_request("POST", "api/games", data=game_data)

        logger.info(
            "Game created successfully",
            extra={
                "game_id": result.get("id"),
                "home_team": result.get("home_team"),
                "away_team": result.get("away_team"),
            }
        )

        return result

    async def update_score(self, game_id: str, score_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update the score for an existing game.

        Args:
            game_id: ID of the game to update
            score_data: Score information dictionary

        Returns:
            Updated game data from API response

        Raises:
            MissingTableAPIError: If score update fails
        """
        logger.info(
            "Updating game score",
            extra={
                "game_id": game_id,
                "home_score": score_data.get("home_score"),
                "away_score": score_data.get("away_score"),
            }
        )

        endpoint = f"api/games/{game_id}/score"
        result = await self._make_request("PUT", endpoint, data=score_data)

        logger.info(
            "Score updated successfully",
            extra={
                "game_id": game_id,
                "home_score": result.get("home_score"),
                "away_score": result.get("away_score"),
            }
        )

        return result

    async def get_game(self, game_id: str) -> Dict[str, Any]:
        """
        Retrieve a game by ID.

        Args:
            game_id: ID of the game to retrieve

        Returns:
            Game data from API response

        Raises:
            MissingTableAPIError: If game retrieval fails
        """
        logger.debug("Retrieving game", extra={"game_id": game_id})

        endpoint = f"api/games/{game_id}"
        result = await self._make_request("GET", endpoint)

        return result

    async def list_games(self, **filters) -> List[Dict[str, Any]]:
        """
        List games with optional filters.

        Args:
            **filters: Query parameters for filtering games

        Returns:
            List of games from API response

        Raises:
            MissingTableAPIError: If games listing fails
        """
        logger.debug("Listing games", extra={"filters": filters})

        result = await self._make_request("GET", "api/games", params=filters)

        # Assume the API returns a list directly or in a 'games' field
        if isinstance(result, list):
            return result
        return result.get("games", [])