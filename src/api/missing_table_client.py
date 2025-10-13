"""
MissingTable.com API client for match data integration.

This module provides a client for communicating with the missing-table.com API
to create matches, update scores, and manage match data with proper authentication,
error handling, and retry logic.
"""

import asyncio
import os
import time
from typing import Any, Optional
from urllib.parse import urljoin

import httpx
from pydantic import BaseModel

from ..utils.logger import get_logger
from ..utils.metrics import get_metrics

logger = get_logger()
metrics = get_metrics()


class HealthStatus(BaseModel):
    """Health check response model."""

    status: str
    version: Optional[str] = None
    database: Optional[str] = None
    timestamp: Optional[str] = None


class MissingTableAPIError(Exception):
    """Base exception for MissingTable API errors."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        response_data: Optional[dict] = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data


class MissingTableClient:
    """
    Client for interacting with the missing-table.com API.

    Provides methods for health checks, match creation, score updates,
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
        self.base_url = base_url or os.getenv(
            "MISSING_TABLE_API_BASE_URL", "http://localhost:8000"
        )
        self.api_token = api_token or os.getenv("MISSING_TABLE_API_TOKEN")
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_backoff_base = retry_backoff_base

        # Ensure base URL ends with /
        if not self.base_url.endswith("/"):
            self.base_url += "/"

        if not self.api_token:
            logger.warning(
                "No API token provided. Set MISSING_TABLE_API_TOKEN environment variable."
            )

    @property
    def headers(self) -> dict[str, str]:
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
            },
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
                    },
                )

                return HealthStatus(**health_data)

        except httpx.HTTPStatusError as e:
            error_msg = f"Health check failed with status {e.response.status_code}"
            logger.error(
                error_msg,
                extra={
                    "status_code": e.response.status_code,
                    "response_text": e.response.text,
                },
            )
            raise MissingTableAPIError(
                error_msg,
                status_code=e.response.status_code,
                response_data=e.response.json() if e.response.content else None,
            ) from e

        except httpx.RequestError as e:
            error_msg = f"Health check request failed: {str(e)}"
            logger.error(error_msg, extra={"error": str(e)})
            raise MissingTableAPIError(error_msg) from e

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[dict[str, Any]] = None,
        params: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
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
            raise MissingTableAPIError(
                "API token is required for authenticated requests"
            )

        url = urljoin(self.base_url, endpoint)
        start_time = time.time()

        for attempt in range(self.max_retries + 1):
            try:
                logger.debug(
                    f"Making {method} request to {endpoint}",
                    extra={
                        "attempt": attempt + 1,
                        "max_retries": self.max_retries + 1,
                        "url": url,
                        "has_data": data is not None,
                    },
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

                    result: dict[str, Any] = response.json()

                    # Record successful API call metrics
                    duration = time.time() - start_time
                    metrics.record_api_call(
                        endpoint=endpoint,
                        method=method,
                        status_code=response.status_code,
                        duration_seconds=duration,
                    )

                    logger.info(
                        f"{method} request successful",
                        extra={
                            "endpoint": endpoint,
                            "status_code": response.status_code,
                            "attempt": attempt + 1,
                        },
                    )

                    return result

            except httpx.HTTPStatusError as e:
                # Record failed API call metrics
                duration = time.time() - start_time
                metrics.record_api_call(
                    endpoint=endpoint,
                    method=method,
                    status_code=e.response.status_code,
                    duration_seconds=duration,
                )

                if e.response.status_code < 500 or attempt == self.max_retries:
                    # Don't retry client errors (4xx) or if we've exhausted retries
                    error_msg = f"{method} {endpoint} failed with status {e.response.status_code}"
                    logger.error(
                        error_msg,
                        extra={
                            "status_code": e.response.status_code,
                            "response_text": e.response.text,
                            "attempt": attempt + 1,
                        },
                    )
                    raise MissingTableAPIError(
                        error_msg,
                        status_code=e.response.status_code,
                        response_data=e.response.json() if e.response.content else None,
                    ) from e

                # Server error, retry with backoff
                delay = self.retry_backoff_base * (2**attempt)
                logger.warning(
                    f"Server error on attempt {attempt + 1}, retrying in {delay}s",
                    extra={
                        "status_code": e.response.status_code,
                        "attempt": attempt + 1,
                        "delay": delay,
                    },
                )
                await asyncio.sleep(delay)

            except httpx.RequestError as e:
                # Record failed API call metrics (network error - no status code)
                duration = time.time() - start_time
                metrics.record_api_call(
                    endpoint=endpoint,
                    method=method,
                    status_code=0,  # Use 0 to indicate network error
                    duration_seconds=duration,
                )

                if attempt == self.max_retries:
                    error_msg = f"{method} {endpoint} request failed: {str(e)}"
                    # Log at debug level to avoid cluttering CLI output - higher level will show user-friendly error
                    logger.debug(
                        error_msg, extra={"error": str(e), "attempt": attempt + 1}
                    )
                    raise MissingTableAPIError(error_msg) from e

                # Network error, retry with backoff
                delay = self.retry_backoff_base * (2**attempt)
                logger.warning(
                    f"Network error on attempt {attempt + 1}, retrying in {delay}s",
                    extra={
                        "error": str(e),
                        "attempt": attempt + 1,
                        "delay": delay,
                    },
                )
                await asyncio.sleep(delay)

        # Should not reach here
        raise MissingTableAPIError(
            f"Request failed after {self.max_retries + 1} attempts"
        )

    async def create_match(self, match_data: dict[str, Any]) -> dict[str, Any]:
        """
        Create a new match in the missing-table API.

        Args:
            match_data: Match information dictionary

        Returns:
            Created match data from API response

        Raises:
            MissingTableAPIError: If match creation fails
        """
        logger.info(
            "Creating new match",
            extra={
                "home_team": match_data.get("home_team"),
                "away_team": match_data.get("away_team"),
                "match_date": match_data.get("match_date"),
            },
        )

        result = await self._make_request("POST", "api/matches", data=match_data)

        logger.info(
            "Match created successfully",
            extra={
                "match_id": result.get("id"),
                "home_team": result.get("home_team"),
                "away_team": result.get("away_team"),
            },
        )

        return result

    async def update_match_score(
        self, match_id: str, score_data: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Update the score for an existing match using PATCH.

        Args:
            match_id: ID of the match to update
            score_data: Score information dictionary (can include home_score, away_score, match_status)

        Returns:
            Updated match data from API response

        Raises:
            MissingTableAPIError: If score update fails
        """
        logger.info(
            "Updating match score",
            extra={
                "match_id": match_id,
                "home_score": score_data.get("home_score"),
                "away_score": score_data.get("away_score"),
            },
        )

        endpoint = f"api/matches/{match_id}"
        result = await self._make_request("PATCH", endpoint, data=score_data)

        logger.info(
            "Score updated successfully",
            extra={
                "match_id": match_id,
                "home_score": result.get("home_score"),
                "away_score": result.get("away_score"),
            },
        )

        return result

    async def get_match(self, match_id: str) -> dict[str, Any]:
        """
        Retrieve a match by ID.

        Args:
            match_id: ID of the match to retrieve

        Returns:
            Match data from API response

        Raises:
            MissingTableAPIError: If match retrieval fails
        """
        logger.debug("Retrieving match", extra={"match_id": match_id})

        endpoint = f"api/matches/{match_id}"
        result = await self._make_request("GET", endpoint)

        return result

    async def list_matches(self, **filters: Any) -> list[dict[str, Any]]:
        """
        List matches with optional filters.

        Args:
            **filters: Query parameters for filtering matches

        Returns:
            List of matches from API response

        Raises:
            MissingTableAPIError: If matches listing fails
        """
        logger.debug("Listing matches", extra={"filters": filters})

        result = await self._make_request("GET", "api/matches", params=filters)

        # Assume the API returns a list directly or in a 'matches' field
        if isinstance(result, list):
            matches_list: list[dict[str, Any]] = result
            return matches_list
        matches_from_dict: list[dict[str, Any]] = result.get("matches", [])
        return matches_from_dict

    async def submit_match_async(
        self, match_data: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Submit a match for asynchronous processing via Celery workers.

        This method posts to the /api/matches/submit endpoint which queues
        the match for processing and returns immediately with a task ID.

        Args:
            match_data: Match information dictionary with team names (not IDs)
                Required fields: home_team, away_team, match_date, season
                Optional: age_group, division, home_score, away_score, etc.

        Returns:
            Dictionary containing:
                - task_id: Celery task ID for status polling
                - status_url: URL to check task status
                - match: Echo of submitted match data

        Raises:
            MissingTableAPIError: If submission fails

        Example:
            >>> match_data = {
            ...     "home_team": "Team A",
            ...     "away_team": "Team B",
            ...     "match_date": "2025-10-25T15:00:00Z",
            ...     "season": "2025-26",
            ...     "age_group": "U14",
            ...     "external_match_id": "mls-12345"
            ... }
            >>> result = await client.submit_match_async(match_data)
            >>> task_id = result["task_id"]
        """
        logger.info(
            "Submitting match for async processing",
            extra={
                "home_team": match_data.get("home_team"),
                "away_team": match_data.get("away_team"),
                "match_date": match_data.get("match_date"),
            },
        )

        result = await self._make_request(
            "POST", "api/matches/submit", data=match_data
        )

        logger.info(
            "Match submitted successfully",
            extra={
                "task_id": result.get("task_id"),
                "status_url": result.get("status_url"),
            },
        )

        return result

    async def get_task_status(self, task_id: str) -> dict[str, Any]:
        """
        Check the status of an async match processing task.

        Args:
            task_id: The Celery task ID returned from submit_match_async

        Returns:
            Dictionary containing:
                - task_id: The task ID
                - state: Task state (PENDING, SUCCESS, FAILURE, etc.)
                - ready: Boolean indicating if task is complete
                - result: Match creation result if successful
                - error: Error message if failed

        Raises:
            MissingTableAPIError: If status check fails

        Example:
            >>> status = await client.get_task_status(task_id)
            >>> if status["ready"] and status.get("result"):
            ...     match_id = status["result"]["match_id"]
        """
        logger.debug("Checking task status", extra={"task_id": task_id})

        endpoint = f"api/matches/task/{task_id}"
        result = await self._make_request("GET", endpoint)

        return result
