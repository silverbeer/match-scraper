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

    Supports two routing modes:
    1. Fanout Exchange: Publish to exchange that routes to multiple queues (prod + dev)
    2. Direct Queue: Publish directly to a specific queue (for manual targeting)
    """

    def __init__(
        self,
        broker_url: Optional[str] = None,
        exchange_name: Optional[str] = None,
        queue_name: Optional[str] = None,
    ) -> None:
        """
        Initialize Celery client.

        Args:
            broker_url: RabbitMQ connection URL. Format: amqp://user:pass@host:port//
                       Defaults to RABBITMQ_URL env var. Required if not provided.
            exchange_name: Name of fanout exchange to publish to (e.g., "matches-fanout").
                          If set, messages go to exchange which routes to all bound queues.
            queue_name: Name of specific queue to publish to (e.g., "matches.dev").
                       If set, messages go directly to this queue only.

        Note: If both exchange_name and queue_name are provided, exchange_name takes precedence.
              If neither is provided, defaults to exchange_name="matches-fanout".

        Raises:
            ValueError: If broker_url is not provided and RABBITMQ_URL env var is not set

        Example:
            # Fanout to both dev and prod (default)
            client = MatchQueueClient()

            # Target specific queue
            client = MatchQueueClient(queue_name="matches.dev")

            # Custom exchange
            client = MatchQueueClient(exchange_name="matches-testing")
        """
        self.broker_url = broker_url or os.getenv("RABBITMQ_URL")

        if not self.broker_url:
            raise ValueError(
                "RabbitMQ connection URL is required. "
                "Set RABBITMQ_URL environment variable or pass broker_url parameter. "
                "Format: amqp://user:password@host:port//"
            )

        # Configure routing: exchange takes precedence, fallback to default fanout
        self.exchange_name = exchange_name or (None if queue_name else "matches-fanout")
        self.queue_name = queue_name

        # Create Celery app (producer only, no tasks defined)
        self.app = Celery("match_scraper", broker=self.broker_url)

        # Configure Celery routing
        celery_config = {
            # Don't wait for task results (fire and forget)
            "task_ignore_result": True,
            # Use JSON for serialization (safer than pickle)
            "task_serializer": "json",
            "accept_content": ["json"],
            "result_serializer": "json",
            # Connection settings
            "broker_connection_retry": True,
            "broker_connection_retry_on_startup": True,
            "broker_connection_max_retries": 10,
        }

        # If using exchange, configure default exchange for all tasks
        if self.exchange_name:
            celery_config["task_default_exchange"] = self.exchange_name
            celery_config["task_default_exchange_type"] = "fanout"
            celery_config["task_default_routing_key"] = ""
            # Override default queue behavior
            celery_config["task_default_queue"] = (
                ""  # Empty string to force exchange routing
            )
            celery_config["task_create_missing_queues"] = False

        self.app.conf.update(celery_config)

        routing_info = (
            f"exchange={self.exchange_name}"
            if self.exchange_name
            else f"queue={self.queue_name}"
        )
        print(
            f"✓ Celery client initialized with broker: {self._safe_broker_url()}, routing: {routing_info}"
        )

    def _safe_broker_url(self) -> str:
        """Return broker URL with password masked for logging."""
        # broker_url is guaranteed to be set by __init__ (raises ValueError if not)
        assert self.broker_url is not None
        return self.broker_url.replace(
            self.broker_url.split("@")[0].split(":")[-1], "***"
        )

    def submit_match(self, match_data: dict) -> str:
        """
        Submit match data to RabbitMQ queue or exchange.

        This is the key method - it validates and sends a message.
        Routing depends on how client was initialized (exchange vs. queue).

        Args:
            match_data: Match data dictionary (will be validated against MatchData model)

        Returns:
            Task ID for tracking (can be used to check status in worker)

        Raises:
            ValidationError: If match_data doesn't match schema

        Example:
            >>> # Fanout to all environments (default)
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

            >>> # Target dev only
            >>> client = MatchQueueClient(queue_name="matches.dev")
            >>> task_id = client.submit_match({...})
        """
        # Step 1: Validate before sending (fail fast!)
        try:
            validated = MatchData(**match_data)
        except ValidationError as e:
            print(f"✗ Validation failed: {e}")
            raise

        # Step 2: Prepare task parameters
        task_kwargs = {
            "name": "celery_tasks.match_tasks.process_match_data",
            "args": [validated.model_dump(mode="json")],
        }

        # Step 3: Configure routing based on client configuration
        if self.exchange_name:
            # Fanout exchange pattern: Use pure AMQP via pika to bypass Celery entirely
            # Celery doesn't know about the fanout exchange, so we publish directly to RabbitMQ
            import json
            from uuid import uuid4

            import pika

            task_id = str(uuid4())
            routing_target = f"exchange '{self.exchange_name}'"

            # Parse broker URL for pika connection
            # Format: amqp://user:pass@host:port//
            assert self.broker_url is not None  # Guaranteed by __init__
            broker_parts = self.broker_url.replace("amqp://", "").split("@")
            credentials_part = broker_parts[0]
            host_part = broker_parts[1].rstrip("/")

            username, password = credentials_part.split(":")
            host = host_part.split(":")[0] if ":" in host_part else host_part
            port = int(host_part.split(":")[1]) if ":" in host_part else 5672

            # Create pika connection and publish
            credentials = pika.PlainCredentials(username, password)
            parameters = pika.ConnectionParameters(
                host=host, port=port, credentials=credentials
            )

            connection = pika.BlockingConnection(parameters)
            channel = connection.channel()

            # Publish Celery-formatted task message
            message = {
                "id": task_id,
                "task": "celery_tasks.match_tasks.process_match_data",
                "args": [validated.model_dump(mode="json")],
                "kwargs": {},
                "retries": 0,
                "eta": None,
                "expires": None,
            }

            channel.basic_publish(
                exchange=self.exchange_name,
                routing_key="",  # Empty for fanout
                body=json.dumps(message),
                properties=pika.BasicProperties(
                    delivery_mode=2,  # Persistent
                    content_type="application/json",
                    content_encoding="utf-8",
                ),
            )

            connection.close()

            print(f"✓ Match submitted to {routing_target}: {task_id}")
            return task_id
        else:
            # Direct queue pattern: message goes to specific queue
            # queue_name must be set when not using exchange (checked in __init__)
            assert self.queue_name is not None
            task_kwargs["queue"] = self.queue_name
            task_kwargs["routing_key"] = f"{self.queue_name}.process"
            routing_target = f"queue '{self.queue_name}'"

            # Step 4: Send to RabbitMQ
            result = self.app.send_task(**task_kwargs)
            print(f"✓ Match submitted to {routing_target}: {result.id}")
            # result.id is typed as Any but is actually str
            return str(result.id)

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
