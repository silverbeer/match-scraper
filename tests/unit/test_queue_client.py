"""Unit tests for queue client."""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from src.celery.queue_client import MatchQueueClient


class TestMatchQueueClientInit:
    """Test cases for MatchQueueClient initialization."""

    def test_init_with_broker_url_env_var(self, monkeypatch):
        """Test initialization using RABBITMQ_URL environment variable."""
        monkeypatch.setenv("RABBITMQ_URL", "amqp://user:pass@localhost:5672//")

        with patch("src.celery.queue_client.Celery") as mock_celery:
            client = MatchQueueClient()

            assert client.broker_url == "amqp://user:pass@localhost:5672//"
            assert client.exchange_name == "matches-fanout"
            assert client.queue_name is None
            mock_celery.assert_called_once_with(
                "match_scraper", broker="amqp://user:pass@localhost:5672//"
            )

    def test_init_with_explicit_broker_url(self):
        """Test initialization with explicitly provided broker_url."""
        with patch("src.celery.queue_client.Celery"):
            client = MatchQueueClient(broker_url="amqp://admin:secret@mq:5672//")

            assert client.broker_url == "amqp://admin:secret@mq:5672//"

    def test_init_missing_broker_url_raises_error(self, monkeypatch):
        """Test that missing broker URL raises ValueError."""
        monkeypatch.delenv("RABBITMQ_URL", raising=False)

        with pytest.raises(ValueError) as exc_info:
            MatchQueueClient()

        assert "RabbitMQ connection URL is required" in str(exc_info.value)
        assert "RABBITMQ_URL environment variable" in str(exc_info.value)

    def test_init_default_fanout_exchange(self, monkeypatch):
        """Test that default routing uses fanout exchange."""
        monkeypatch.setenv("RABBITMQ_URL", "amqp://user:pass@localhost:5672//")

        with patch("src.celery.queue_client.Celery"):
            client = MatchQueueClient()

            assert client.exchange_name == "matches-fanout"
            assert client.queue_name is None

    def test_init_with_custom_exchange(self, monkeypatch):
        """Test initialization with custom exchange name."""
        monkeypatch.setenv("RABBITMQ_URL", "amqp://user:pass@localhost:5672//")

        with patch("src.celery.queue_client.Celery"):
            client = MatchQueueClient(exchange_name="matches-testing")

            assert client.exchange_name == "matches-testing"
            assert client.queue_name is None

    def test_init_with_queue_name(self, monkeypatch):
        """Test initialization with specific queue name."""
        monkeypatch.setenv("RABBITMQ_URL", "amqp://user:pass@localhost:5672//")

        with patch("src.celery.queue_client.Celery"):
            client = MatchQueueClient(queue_name="matches.dev")

            assert client.queue_name == "matches.dev"
            assert client.exchange_name is None

    def test_init_exchange_takes_precedence_over_queue(self, monkeypatch):
        """Test that exchange_name takes precedence when both are provided."""
        monkeypatch.setenv("RABBITMQ_URL", "amqp://user:pass@localhost:5672//")

        with patch("src.celery.queue_client.Celery"):
            client = MatchQueueClient(
                exchange_name="matches-fanout", queue_name="matches.dev"
            )

            assert client.exchange_name == "matches-fanout"
            assert client.queue_name == "matches.dev"

    def test_safe_broker_url_masks_password(self, monkeypatch):
        """Test that _safe_broker_url masks the password."""
        monkeypatch.setenv(
            "RABBITMQ_URL", "amqp://admin:secretpassword@localhost:5672//"
        )

        with patch("src.celery.queue_client.Celery"):
            client = MatchQueueClient()
            safe_url = client._safe_broker_url()

            assert "secretpassword" not in safe_url
            assert "***" in safe_url
            assert "admin" in safe_url
            assert "localhost" in safe_url

    def test_celery_config_for_exchange(self, monkeypatch):
        """Test Celery configuration when using exchange routing."""
        monkeypatch.setenv("RABBITMQ_URL", "amqp://user:pass@localhost:5672//")

        with patch("src.celery.queue_client.Celery") as mock_celery:
            mock_app = MagicMock()
            mock_celery.return_value = mock_app

            MatchQueueClient(exchange_name="test-exchange")

            # Verify Celery config was updated
            mock_app.conf.update.assert_called_once()
            config = mock_app.conf.update.call_args[0][0]

            assert config["task_default_exchange"] == "test-exchange"
            assert config["task_default_exchange_type"] == "fanout"
            assert config["task_default_routing_key"] == ""
            assert config["task_serializer"] == "json"
            assert config["task_ignore_result"] is True


class TestMatchQueueClientSubmission:
    """Test cases for submitting matches to the queue."""

    @pytest.fixture
    def sample_match_data(self):
        """Fixture providing valid match data."""
        return {
            "home_team": "Team A",
            "away_team": "Team B",
            "match_date": date(2025, 11, 15),
            "season": "2024-25",
            "age_group": "U14",
            "match_type": "League",
            "division": "Northeast",
        }

    @pytest.fixture
    def sample_match_with_division_id(self):
        """Fixture providing match data with division_id."""
        return {
            "home_team": "Rochester NY FC Academy",
            "away_team": "Boston United",
            "match_date": date(2025, 11, 15),
            "season": "2024-25",
            "age_group": "U14",
            "match_type": "League",
            "division": "Northeast",
            "division_id": 41,
        }

    @pytest.fixture
    def queue_client(self, monkeypatch):
        """Fixture providing a configured queue client."""
        monkeypatch.setenv("RABBITMQ_URL", "amqp://user:pass@localhost:5672//")

        with patch("src.celery.queue_client.Celery"):
            return MatchQueueClient(queue_name="matches.test")

    def test_submit_match_with_valid_data(
        self, queue_client, sample_match_data, monkeypatch
    ):
        """Test submitting a valid match to direct queue."""
        mock_result = MagicMock()
        mock_result.id = "test-task-id-123"
        queue_client.app.send_task = MagicMock(return_value=mock_result)

        task_id = queue_client.submit_match(sample_match_data)

        assert task_id == "test-task-id-123"
        queue_client.app.send_task.assert_called_once()

        # Verify task parameters
        call_args = queue_client.app.send_task.call_args
        assert call_args[1]["name"] == "celery_tasks.match_tasks.process_match_data"
        assert call_args[1]["queue"] == "matches.test"
        assert call_args[1]["routing_key"] == "matches.test.process"

    def test_submit_match_with_division_id(
        self, queue_client, sample_match_with_division_id
    ):
        """Test submitting a match with division_id field."""
        mock_result = MagicMock()
        mock_result.id = "task-with-division-id"
        queue_client.app.send_task = MagicMock(return_value=mock_result)

        task_id = queue_client.submit_match(sample_match_with_division_id)

        assert task_id == "task-with-division-id"

        # Verify division_id is in the submitted data
        call_args = queue_client.app.send_task.call_args
        submitted_data = call_args[1]["args"][0]
        assert submitted_data["division_id"] == 41
        assert submitted_data["division"] == "Northeast"

    def test_submit_match_validation_failure(self, queue_client):
        """Test that invalid match data raises ValidationError."""
        invalid_data = {
            "home_team": "Team A",
            # Missing required fields
        }

        with pytest.raises(ValidationError):
            queue_client.submit_match(invalid_data)

    def test_submit_match_to_exchange_fanout(self, monkeypatch, sample_match_data):
        """Test submitting match to fanout exchange using pika."""
        monkeypatch.setenv("RABBITMQ_URL", "amqp://user:pass@localhost:5672//")

        with (
            patch("src.celery.queue_client.Celery"),
            patch("pika.BlockingConnection") as mock_blocking_conn,
            patch("pika.PlainCredentials"),
            patch("pika.ConnectionParameters"),
            patch("pika.BasicProperties"),
        ):
            # Setup mock pika connection
            mock_connection = MagicMock()
            mock_channel = MagicMock()
            mock_connection.channel.return_value = mock_channel
            mock_blocking_conn.return_value = mock_connection

            client = MatchQueueClient(exchange_name="matches-fanout")
            task_id = client.submit_match(sample_match_data)

            # Verify pika was used for fanout
            mock_blocking_conn.assert_called_once()
            mock_channel.basic_publish.assert_called_once()

            # Verify message structure
            call_kwargs = mock_channel.basic_publish.call_args[1]
            assert call_kwargs["exchange"] == "matches-fanout"
            assert call_kwargs["routing_key"] == ""

            # Verify task_id is a UUID string
            assert isinstance(task_id, str)
            assert len(task_id) == 36  # UUID format

    def test_submit_match_generates_task_id(self, queue_client, sample_match_data):
        """Test that submit_match returns a task ID."""
        mock_result = MagicMock()
        mock_result.id = "generated-task-id"
        queue_client.app.send_task = MagicMock(return_value=mock_result)

        task_id = queue_client.submit_match(sample_match_data)

        assert task_id is not None
        assert isinstance(task_id, str)
        assert len(task_id) > 0

    def test_submit_match_formats_celery_message_correctly(
        self, queue_client, sample_match_data
    ):
        """Test that Celery message is formatted with correct structure."""
        mock_result = MagicMock()
        mock_result.id = "task-123"
        queue_client.app.send_task = MagicMock(return_value=mock_result)

        queue_client.submit_match(sample_match_data)

        # Verify message structure
        call_args = queue_client.app.send_task.call_args[1]
        assert "name" in call_args
        assert "args" in call_args
        assert "queue" in call_args
        assert "routing_key" in call_args

        # Verify args contain validated match data
        args = call_args["args"]
        assert len(args) == 1
        assert isinstance(args[0], dict)
        assert "home_team" in args[0]
        assert "away_team" in args[0]


class TestMatchQueueClientBatch:
    """Test cases for batch match submission."""

    @pytest.fixture
    def queue_client(self, monkeypatch):
        """Fixture providing a configured queue client."""
        monkeypatch.setenv("RABBITMQ_URL", "amqp://user:pass@localhost:5672//")

        with patch("src.celery.queue_client.Celery"):
            return MatchQueueClient(queue_name="matches.test")

    @pytest.fixture
    def sample_matches(self):
        """Fixture providing a list of valid match data."""
        return [
            {
                "home_team": f"Team {i}",
                "away_team": f"Team {i + 1}",
                "match_date": date(2025, 11, 15),
                "season": "2024-25",
                "age_group": "U14",
                "match_type": "League",
            }
            for i in range(3)
        ]

    def test_submit_matches_batch_all_success(self, queue_client, sample_matches):
        """Test batch submission when all matches succeed."""
        mock_result = MagicMock()
        mock_result.id = "task-id"
        queue_client.app.send_task = MagicMock(return_value=mock_result)

        task_ids = queue_client.submit_matches_batch(sample_matches)

        assert len(task_ids) == 3
        assert all(task_id == "task-id" for task_id in task_ids)
        assert queue_client.app.send_task.call_count == 3

    def test_submit_matches_batch_partial_failure(self, queue_client):
        """Test batch submission continues when some matches fail validation."""
        matches = [
            {
                "home_team": "Team A",
                "away_team": "Team B",
                "match_date": date(2025, 11, 15),
                "season": "2024-25",
                "age_group": "U14",
                "match_type": "League",
            },
            {
                # Invalid - missing required fields
                "home_team": "Team C",
            },
            {
                "home_team": "Team D",
                "away_team": "Team E",
                "match_date": date(2025, 11, 15),
                "season": "2024-25",
                "age_group": "U14",
                "match_type": "League",
            },
        ]

        mock_result = MagicMock()
        mock_result.id = "task-id"
        queue_client.app.send_task = MagicMock(return_value=mock_result)

        task_ids = queue_client.submit_matches_batch(matches)

        # Should have 2 successful submissions (skipping the invalid one)
        assert len(task_ids) == 2
        assert queue_client.app.send_task.call_count == 2

    def test_submit_matches_batch_validation_errors(self, queue_client):
        """Test batch submission handles validation errors gracefully."""
        invalid_matches = [
            {"home_team": "Team A"},  # Missing required fields
            {"away_team": "Team B"},  # Missing required fields
        ]

        task_ids = queue_client.submit_matches_batch(invalid_matches)

        # All should fail validation
        assert len(task_ids) == 0

    def test_submit_matches_batch_returns_task_ids(self, queue_client, sample_matches):
        """Test that batch submission returns list of task IDs."""
        mock_result = MagicMock()
        mock_result.id = "task-id-123"
        queue_client.app.send_task = MagicMock(return_value=mock_result)

        task_ids = queue_client.submit_matches_batch(sample_matches)

        assert isinstance(task_ids, list)
        assert all(isinstance(task_id, str) for task_id in task_ids)

    def test_submit_matches_batch_continues_on_error(self, queue_client):
        """Test that batch submission continues even if individual submissions fail."""
        matches = [
            {
                "home_team": "Team A",
                "away_team": "Team B",
                "match_date": date(2025, 11, 15),
                "season": "2024-25",
                "age_group": "U14",
                "match_type": "League",
            },
            {
                "home_team": "Team C",
                "away_team": "Team D",
                "match_date": date(2025, 11, 15),
                "season": "2024-25",
                "age_group": "U14",
                "match_type": "League",
            },
        ]

        # First submission succeeds, second fails
        mock_result = MagicMock()
        mock_result.id = "task-id"
        queue_client.app.send_task = MagicMock(
            side_effect=[mock_result, Exception("Connection error")]
        )

        task_ids = queue_client.submit_matches_batch(matches)

        # Should have 1 successful submission
        assert len(task_ids) == 1
        assert queue_client.app.send_task.call_count == 2


class TestMatchQueueClientConnection:
    """Test cases for connection checking."""

    @pytest.fixture
    def queue_client(self, monkeypatch):
        """Fixture providing a configured queue client."""
        monkeypatch.setenv("RABBITMQ_URL", "amqp://user:pass@localhost:5672//")

        with patch("src.celery.queue_client.Celery"):
            return MatchQueueClient(queue_name="matches.test")

    def test_check_connection_success(self, queue_client):
        """Test successful connection check."""
        mock_connection = MagicMock()
        mock_connection.ensure_connection = MagicMock(return_value=True)
        queue_client.app.connection = MagicMock(return_value=mock_connection)

        result = queue_client.check_connection()

        assert result is True
        mock_connection.ensure_connection.assert_called_once_with(max_retries=3)

    def test_check_connection_failure(self, queue_client):
        """Test connection check when connection fails."""
        mock_connection = MagicMock()
        mock_connection.ensure_connection = MagicMock(
            side_effect=Exception("Connection refused")
        )
        queue_client.app.connection = MagicMock(return_value=mock_connection)

        result = queue_client.check_connection()

        assert result is False

    def test_check_connection_timeout(self, queue_client):
        """Test connection check with timeout error."""
        mock_connection = MagicMock()
        mock_connection.ensure_connection = MagicMock(
            side_effect=TimeoutError("Connection timeout")
        )
        queue_client.app.connection = MagicMock(return_value=mock_connection)

        result = queue_client.check_connection()

        assert result is False


class TestMatchQueueClientDivisionId:
    """Test cases for division_id feature integration."""

    @pytest.fixture
    def queue_client(self, monkeypatch):
        """Fixture providing a configured queue client."""
        monkeypatch.setenv("RABBITMQ_URL", "amqp://user:pass@localhost:5672//")

        with patch("src.celery.queue_client.Celery"):
            return MatchQueueClient(queue_name="matches.test")

    def test_submit_homegrown_match_with_division_id(self, queue_client):
        """Test submitting Homegrown league match with division_id."""
        match_data = {
            "home_team": "Team A",
            "away_team": "Team B",
            "match_date": date(2025, 11, 15),
            "season": "2024-25",
            "age_group": "U14",
            "match_type": "League",
            "division": "Northeast",
            "division_id": 41,
        }

        mock_result = MagicMock()
        mock_result.id = "task-id"
        queue_client.app.send_task = MagicMock(return_value=mock_result)

        task_id = queue_client.submit_match(match_data)

        assert task_id is not None

        # Verify division_id is preserved
        call_args = queue_client.app.send_task.call_args[1]
        submitted_data = call_args["args"][0]
        assert submitted_data["division_id"] == 41

    def test_submit_academy_match_with_conference_id(self, queue_client):
        """Test submitting Academy league match with division_id (from conference)."""
        match_data = {
            "home_team": "Rochester NY FC Academy",
            "away_team": "Boston United",
            "match_date": date(2025, 11, 15),
            "season": "2024-25",
            "age_group": "U14",
            "match_type": "League",
            "division": "New England",  # Academy uses conference name
            "division_id": 41,  # New England maps to 41
        }

        mock_result = MagicMock()
        mock_result.id = "task-id"
        queue_client.app.send_task = MagicMock(return_value=mock_result)

        task_id = queue_client.submit_match(match_data)

        assert task_id is not None

        # Verify division_id is preserved
        call_args = queue_client.app.send_task.call_args[1]
        submitted_data = call_args["args"][0]
        assert submitted_data["division_id"] == 41
        assert submitted_data["division"] == "New England"

    def test_division_id_included_in_message_payload(self, queue_client):
        """Test that division_id is included in the Celery message payload."""
        match_data = {
            "home_team": "Team A",
            "away_team": "Team B",
            "match_date": date(2025, 11, 15),
            "season": "2024-25",
            "age_group": "U14",
            "match_type": "League",
            "division": "Central",
            "division_id": 34,
        }

        mock_result = MagicMock()
        mock_result.id = "task-id"
        queue_client.app.send_task = MagicMock(return_value=mock_result)

        queue_client.submit_match(match_data)

        # Verify the complete message structure
        call_args = queue_client.app.send_task.call_args[1]
        message = call_args["args"][0]

        assert "division_id" in message
        assert message["division_id"] == 34
        assert "division" in message
        assert message["division"] == "Central"

    def test_division_id_validation_through_pydantic(self, queue_client):
        """Test that invalid division_id values are caught by Pydantic validation."""
        invalid_match_data = {
            "home_team": "Team A",
            "away_team": "Team B",
            "match_date": date(2025, 11, 15),
            "season": "2024-25",
            "age_group": "U14",
            "match_type": "League",
            "division": "Northeast",
            "division_id": -1,  # Invalid: must be >= 1
        }

        with pytest.raises(ValidationError) as exc_info:
            queue_client.submit_match(invalid_match_data)

        assert "division_id" in str(exc_info.value)
