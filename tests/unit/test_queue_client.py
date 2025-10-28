"""Unit tests for RabbitMQ queue client."""

import os
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from src.celery.queue_client import MatchQueueClient


class TestMatchQueueClientInit:
    """Test MatchQueueClient initialization."""

    def test_init_with_broker_url_parameter(self):
        """Test initializing with explicit broker_url parameter."""
        with patch("src.celery.queue_client.Celery") as mock_celery:
            client = MatchQueueClient(broker_url="amqp://user:pass@localhost:5672//")

            assert client.broker_url == "amqp://user:pass@localhost:5672//"
            assert client.exchange_name == "matches-fanout"  # Default fanout
            assert client.queue_name is None
            mock_celery.assert_called_once_with(
                "match_scraper", broker="amqp://user:pass@localhost:5672//"
            )

    def test_init_with_env_var(self):
        """Test initializing with RABBITMQ_URL environment variable."""
        env_vars = {"RABBITMQ_URL": "amqp://envuser:envpass@envhost:5672//"}

        with patch.dict(os.environ, env_vars, clear=True):
            with patch("src.celery.queue_client.Celery"):
                client = MatchQueueClient()

                assert client.broker_url == "amqp://envuser:envpass@envhost:5672//"

    def test_init_missing_broker_url(self):
        """Test that initialization fails without broker URL."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(
                ValueError,
                match="RabbitMQ connection URL is required",
            ):
                MatchQueueClient()

    def test_init_with_exchange_name(self):
        """Test initializing with custom exchange name."""
        with patch("src.celery.queue_client.Celery"):
            client = MatchQueueClient(
                broker_url="amqp://user:pass@localhost:5672//",
                exchange_name="custom-exchange",
            )

            assert client.exchange_name == "custom-exchange"
            assert client.queue_name is None

    def test_init_with_queue_name(self):
        """Test initializing with specific queue name."""
        with patch("src.celery.queue_client.Celery"):
            client = MatchQueueClient(
                broker_url="amqp://user:pass@localhost:5672//", queue_name="matches.dev"
            )

            assert client.exchange_name is None
            assert client.queue_name == "matches.dev"

    def test_init_exchange_takes_precedence(self):
        """Test that exchange_name takes precedence over queue_name."""
        with patch("src.celery.queue_client.Celery"):
            client = MatchQueueClient(
                broker_url="amqp://user:pass@localhost:5672//",
                exchange_name="test-exchange",
                queue_name="test-queue",
            )

            assert client.exchange_name == "test-exchange"
            assert client.queue_name == "test-queue"

    def test_init_celery_config_with_exchange(self):
        """Test Celery configuration when using exchange."""
        with patch("src.celery.queue_client.Celery") as mock_celery:
            mock_app = MagicMock()
            mock_celery.return_value = mock_app

            MatchQueueClient(
                broker_url="amqp://user:pass@localhost:5672//",
                exchange_name="test-exchange",
            )

            # Verify Celery config was updated
            mock_app.conf.update.assert_called_once()
            config = mock_app.conf.update.call_args[0][0]

            assert config["task_default_exchange"] == "test-exchange"
            assert config["task_default_exchange_type"] == "fanout"
            assert config["task_default_routing_key"] == ""
            assert config["task_serializer"] == "json"
            assert config["task_ignore_result"] is True

    def test_init_celery_config_without_exchange(self):
        """Test Celery configuration when using direct queue."""
        with patch("src.celery.queue_client.Celery") as mock_celery:
            mock_app = MagicMock()
            mock_celery.return_value = mock_app

            MatchQueueClient(
                broker_url="amqp://user:pass@localhost:5672//",
                queue_name="test-queue",
            )

            # Verify Celery config was updated
            config = mock_app.conf.update.call_args[0][0]

            # Should not have exchange config
            assert "task_default_exchange" not in config
            assert config["task_serializer"] == "json"


class TestSafeBrokerUrl:
    """Test broker URL password masking."""

    def test_safe_broker_url_masks_password(self):
        """Test that password is masked in broker URL."""
        with patch("src.celery.queue_client.Celery"):
            client = MatchQueueClient(
                broker_url="amqp://user:secretpass@localhost:5672//"
            )

            safe_url = client._safe_broker_url()
            assert "secretpass" not in safe_url
            assert "***" in safe_url
            assert "user" in safe_url
            assert "localhost" in safe_url


class TestSubmitMatch:
    """Test submitting single matches."""

    @patch("pika.BlockingConnection")
    @patch("pika.PlainCredentials")
    @patch("pika.ConnectionParameters")
    @patch("pika.BasicProperties")
    def test_submit_match_with_exchange(
        self,
        mock_basic_props,
        mock_conn_params,
        mock_credentials,
        mock_connection_class,
    ):
        """Test submitting match to exchange (fanout pattern)."""
        # Setup mocks
        mock_connection = MagicMock()
        mock_channel = MagicMock()
        mock_connection_class.return_value = mock_connection
        mock_connection.channel.return_value = mock_channel

        with patch("src.celery.queue_client.Celery"):
            client = MatchQueueClient(
                broker_url="amqp://user:pass@localhost:5672//",
                exchange_name="test-exchange",
            )

            match_data = {
                "home_team": "Team A",
                "away_team": "Team B",
                "match_date": "2025-10-15",
                "season": "2024-25",
                "age_group": "U14",
                "match_type": "League",
            }

            task_id = client.submit_match(match_data)

            # Verify task_id is a UUID string
            assert isinstance(task_id, str)
            assert len(task_id) > 0

            # Verify pika was used to publish
            mock_channel.basic_publish.assert_called_once()
            publish_call = mock_channel.basic_publish.call_args

            assert publish_call[1]["exchange"] == "test-exchange"
            assert publish_call[1]["routing_key"] == ""

    def test_submit_match_with_queue(self):
        """Test submitting match to specific queue."""
        with patch("src.celery.queue_client.Celery") as mock_celery:
            mock_app = MagicMock()
            mock_result = MagicMock()
            mock_result.id = "test-task-id"
            mock_app.send_task.return_value = mock_result
            mock_celery.return_value = mock_app

            client = MatchQueueClient(
                broker_url="amqp://user:pass@localhost:5672//",
                queue_name="matches.dev",
            )

            match_data = {
                "home_team": "Team A",
                "away_team": "Team B",
                "match_date": "2025-10-15",
                "season": "2024-25",
                "age_group": "U14",
                "match_type": "League",
            }

            task_id = client.submit_match(match_data)

            assert task_id == "test-task-id"

            # Verify send_task was called
            mock_app.send_task.assert_called_once()
            call_kwargs = mock_app.send_task.call_args[1]

            assert call_kwargs["queue"] == "matches.dev"
            assert call_kwargs["routing_key"] == "matches.dev.process"
            assert call_kwargs["name"] == "celery_tasks.match_tasks.process_match_data"

    def test_submit_match_validation_error(self):
        """Test that invalid match data raises ValidationError."""
        with patch("src.celery.queue_client.Celery"):
            client = MatchQueueClient(
                broker_url="amqp://user:pass@localhost:5672//",
                queue_name="matches.dev",
            )

            invalid_match_data = {
                "home_team": "Team A",
                # Missing required fields
            }

            with pytest.raises(ValidationError):
                client.submit_match(invalid_match_data)

    @patch("pika.BlockingConnection")
    @patch("pika.PlainCredentials")
    @patch("pika.ConnectionParameters")
    @patch("pika.BasicProperties")
    def test_submit_match_parses_broker_url_correctly(
        self,
        mock_basic_props,
        mock_conn_params,
        mock_credentials,
        mock_connection_class,
    ):
        """Test that broker URL is correctly parsed for pika connection."""
        mock_connection = MagicMock()
        mock_channel = MagicMock()
        mock_connection_class.return_value = mock_connection
        mock_connection.channel.return_value = mock_channel

        with patch("src.celery.queue_client.Celery"):
            client = MatchQueueClient(
                broker_url="amqp://testuser:testpass@testhost:5672//",
                exchange_name="test-exchange",
            )

            match_data = {
                "home_team": "Team A",
                "away_team": "Team B",
                "match_date": "2025-10-15",
                "season": "2024-25",
                "age_group": "U14",
                "match_type": "League",
            }

            client.submit_match(match_data)

            # Verify credentials were created correctly
            mock_credentials.assert_called_once_with("testuser", "testpass")

            # Verify connection parameters were created correctly
            assert mock_conn_params.call_args[1]["host"] == "testhost"
            assert mock_conn_params.call_args[1]["port"] == 5672

    @patch("pika.BlockingConnection")
    @patch("pika.PlainCredentials")
    @patch("pika.ConnectionParameters")
    @patch("pika.BasicProperties")
    def test_submit_match_default_port(
        self,
        mock_basic_props,
        mock_conn_params,
        mock_credentials,
        mock_connection_class,
    ):
        """Test broker URL parsing with default port."""
        mock_connection = MagicMock()
        mock_channel = MagicMock()
        mock_connection_class.return_value = mock_connection
        mock_connection.channel.return_value = mock_channel

        with patch("src.celery.queue_client.Celery"):
            client = MatchQueueClient(
                broker_url="amqp://user:pass@localhost//", exchange_name="test-exchange"
            )

            match_data = {
                "home_team": "Team A",
                "away_team": "Team B",
                "match_date": "2025-10-15",
                "season": "2024-25",
                "age_group": "U14",
                "match_type": "League",
            }

            client.submit_match(match_data)

            # Verify default port 5672 was used
            assert mock_conn_params.call_args[1]["port"] == 5672


class TestSubmitMatchesBatch:
    """Test batch submission of matches."""

    def test_submit_matches_batch_success(self):
        """Test successfully submitting batch of matches."""
        with patch("src.celery.queue_client.Celery") as mock_celery:
            mock_app = MagicMock()
            mock_result1 = MagicMock()
            mock_result1.id = "task-1"
            mock_result2 = MagicMock()
            mock_result2.id = "task-2"
            mock_app.send_task.side_effect = [mock_result1, mock_result2]
            mock_celery.return_value = mock_app

            client = MatchQueueClient(
                broker_url="amqp://user:pass@localhost:5672//",
                queue_name="matches.dev",
            )

            matches = [
                {
                    "home_team": "Team A",
                    "away_team": "Team B",
                    "match_date": "2025-10-15",
                    "season": "2024-25",
                    "age_group": "U14",
                    "match_type": "League",
                },
                {
                    "home_team": "Team C",
                    "away_team": "Team D",
                    "match_date": "2025-10-16",
                    "season": "2024-25",
                    "age_group": "U14",
                    "match_type": "League",
                },
            ]

            task_ids = client.submit_matches_batch(matches)

            assert len(task_ids) == 2
            assert task_ids == ["task-1", "task-2"]

    def test_submit_matches_batch_partial_failure(self):
        """Test batch submission with some failures."""
        with patch("src.celery.queue_client.Celery") as mock_celery:
            mock_app = MagicMock()
            mock_result = MagicMock()
            mock_result.id = "task-1"

            # First succeeds, second fails
            mock_app.send_task.side_effect = [
                mock_result,
                Exception("Connection error"),
            ]
            mock_celery.return_value = mock_app

            client = MatchQueueClient(
                broker_url="amqp://user:pass@localhost:5672//",
                queue_name="matches.dev",
            )

            matches = [
                {
                    "home_team": "Team A",
                    "away_team": "Team B",
                    "match_date": "2025-10-15",
                    "season": "2024-25",
                    "age_group": "U14",
                    "match_type": "League",
                },
                {
                    "home_team": "Team C",
                    "away_team": "Team D",
                    "match_date": "2025-10-16",
                    "season": "2024-25",
                    "age_group": "U14",
                    "match_type": "League",
                },
            ]

            task_ids = client.submit_matches_batch(matches)

            # Only first match should succeed
            assert len(task_ids) == 1
            assert task_ids == ["task-1"]

    def test_submit_matches_batch_empty_list(self):
        """Test submitting empty batch."""
        with patch("src.celery.queue_client.Celery"):
            client = MatchQueueClient(
                broker_url="amqp://user:pass@localhost:5672//",
                queue_name="matches.dev",
            )

            task_ids = client.submit_matches_batch([])

            assert task_ids == []


class TestCheckConnection:
    """Test RabbitMQ connection checking."""

    def test_check_connection_success(self):
        """Test successful connection check."""
        with patch("src.celery.queue_client.Celery") as mock_celery:
            mock_app = MagicMock()
            mock_connection = MagicMock()
            mock_connection.ensure_connection = MagicMock()
            mock_app.connection.return_value = mock_connection
            mock_celery.return_value = mock_app

            client = MatchQueueClient(broker_url="amqp://user:pass@localhost:5672//")

            result = client.check_connection()

            assert result is True
            mock_connection.ensure_connection.assert_called_once_with(max_retries=3)

    def test_check_connection_failure(self):
        """Test connection check failure."""
        with patch("src.celery.queue_client.Celery") as mock_celery:
            mock_app = MagicMock()
            mock_connection = MagicMock()
            mock_connection.ensure_connection.side_effect = Exception(
                "Connection failed"
            )
            mock_app.connection.return_value = mock_connection
            mock_celery.return_value = mock_app

            client = MatchQueueClient(broker_url="amqp://user:pass@localhost:5672//")

            result = client.check_connection()

            assert result is False
