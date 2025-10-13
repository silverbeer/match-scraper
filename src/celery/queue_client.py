"""
Celery client for submitting matches to RabbitMQ.

This client sends messages to the task queue without knowing
the implementation details of the worker. Contract is enforced
via the MatchData Pydantic model and JSON schema.

Key Learning Points:
- Producer: This is the "producer" in a message queue system
- Message passing: We send JSON, not Python objects
- Decoupling: No imports from missing-table repo!
- Task name: Must match worker's @app.task decorator
"""

import os
from typing import Optional

from pydantic import ValidationError

from celery import Celery
from src.models.match_data import MatchData


class MatchQueueClient:
    """
    Client for submitting matches to RabbitMQ/Celery.

    This is a "producer" - it creates messages and sends them to the queue.
    The "consumer" (Celery workers in missing-table) will process them.
    """

    def __init__(self, broker_url: Optional[str] = None) -> None:
        """
        Initialize Celery client.

        Args:
            broker_url: RabbitMQ connection URL. Format: amqp://user:pass@host:port//
                       Defaults to RABBITMQ_URL env var, falls back to localhost.

        Example:
            # Local development
            client = MatchQueueClient("amqp://admin:admin123@localhost:5672//")

            # GKE production
            client = MatchQueueClient("amqp://admin:admin123@messaging-rabbitmq:5672//")
        """
        self.broker_url = broker_url or os.getenv(
            "RABBITMQ_URL", "amqp://admin:admin123@localhost:5672//"
        )

        # Create Celery app (producer only, no tasks defined)
        self.app = Celery("match_scraper", broker=self.broker_url)

        # Configure Celery
        self.app.conf.update(
            # Don't wait for task results (fire and forget)
            task_ignore_result=True,
            # Use JSON for serialization (safer than pickle)
            task_serializer="json",
            accept_content=["json"],
            result_serializer="json",
            # Connection settings
            broker_connection_retry=True,
            broker_connection_retry_on_startup=True,
            broker_connection_max_retries=10,
        )

        print(f"✓ Celery client initialized with broker: {self._safe_broker_url()}")

    def _safe_broker_url(self) -> str:
        """Return broker URL with password masked for logging."""
        return self.broker_url.replace(
            self.broker_url.split("@")[0].split(":")[-1], "***"
        )

    def submit_match(self, match_data: dict) -> str:
        """
        Submit match data to RabbitMQ queue.

        This is the key method - it validates and sends a message to the queue.
        No HTTP API needed!

        Args:
            match_data: Match data dictionary (will be validated against MatchData model)

        Returns:
            Task ID for tracking (can be used to check status in worker)

        Raises:
            ValidationError: If match_data doesn't match schema

        Example:
            >>> client = MatchQueueClient()
            >>> task_id = client.submit_match({
            ...     "home_team": "IFA",
            ...     "away_team": "NEFC",
            ...     "date": "2025-10-15",
            ...     "season": "2024-25",
            ...     "age_group": "U14",
            ...     "match_type": "League"
            ... })
            >>> print(f"Task submitted: {task_id}")
        """
        # Step 1: Validate before sending (fail fast!)
        try:
            validated = MatchData(**match_data)
        except ValidationError as e:
            print(f"✗ Validation failed: {e}")
            raise

        # Step 2: Send to queue
        # IMPORTANT: Task name must match the worker's @app.task(name=...) decorator
        result = self.app.send_task(
            "missing_table.tasks.process_match_data",  # Task name (string, not import!)
            args=[
                validated.model_dump(mode="json")
            ],  # Serialize to JSON-compatible dict
            queue="matches",  # Queue name
            routing_key="matches",  # Routing key (usually same as queue)
        )

        print(f"✓ Match submitted to queue: {result.id}")
        return result.id

    def submit_matches_batch(self, matches: list[dict]) -> list[str]:
        """
        Submit multiple matches in batch.

        This sends each match as a separate task. Workers can process them in parallel.

        Args:
            matches: List of match data dictionaries

        Returns:
            List of task IDs (one per successfully submitted match)

        Example:
            >>> client = MatchQueueClient()
            >>> task_ids = client.submit_matches_batch([
            ...     {"home_team": "A", "away_team": "B", ...},
            ...     {"home_team": "C", "away_team": "D", ...},
            ... ])
            >>> print(f"Submitted {len(task_ids)} matches")
        """
        task_ids = []
        errors = 0

        for i, match_data in enumerate(matches, 1):
            try:
                task_id = self.submit_match(match_data)
                task_ids.append(task_id)
            except Exception as e:
                errors += 1
                print(f"✗ Failed to submit match {i}/{len(matches)}: {e}")
                # Continue with other matches (don't fail entire batch)

        print(f"\n✓ Batch complete: {len(task_ids)} submitted, {errors} failed")
        return task_ids

    def check_connection(self) -> bool:
        """
        Check if RabbitMQ is reachable.

        Returns:
            True if connection successful, False otherwise

        Example:
            >>> client = MatchQueueClient()
            >>> if client.check_connection():
            ...     print("RabbitMQ is up!")
        """
        try:
            # Try to inspect the broker
            self.app.connection().ensure_connection(max_retries=3)
            print("✓ RabbitMQ connection successful")
            return True
        except Exception as e:
            print(f"✗ RabbitMQ connection failed: {e}")
            return False
