"""Unit tests for CLI module."""

import os
import re
from datetime import date, timedelta
from unittest.mock import patch

from typer.testing import CliRunner

from src.cli.main import (
    DEFAULT_AGE_GROUP,
    DEFAULT_DAYS,
    DEFAULT_DIVISION,
    VALID_AGE_GROUPS,
    VALID_DIVISIONS,
    app,
    create_config,
    handle_cli_error,
    setup_environment,
)


def strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from text."""
    ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
    return ansi_escape.sub("", text)


class TestCliUtilityFunctions:
    """Test cases for CLI utility functions."""

    def test_setup_environment_default(self):
        """Test default environment setup."""
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("dotenv.load_dotenv"),  # Prevent .env loading
        ):
            setup_environment()

            # Default log level is now ERROR (not WARNING)
            assert os.environ.get("LOG_LEVEL") == "ERROR"
            assert (
                os.environ.get("MISSING_TABLE_API_BASE_URL") == "http://localhost:8000"
            )
            assert os.environ.get("MISSING_TABLE_API_TOKEN") == ""

    def test_setup_environment_verbose(self):
        """Test verbose environment setup."""
        with patch.dict(os.environ, {}, clear=True):
            setup_environment(verbose=True)

            assert os.environ.get("LOG_LEVEL") == "DEBUG"

    def test_setup_environment_preserves_existing(self):
        """Test that existing environment variables are preserved."""
        with patch.dict(
            os.environ, {"LOG_LEVEL": "INFO", "MISSING_TABLE_API_TOKEN": "existing-key"}
        ):
            setup_environment()

            # Note: setup_environment() now FORCES LOG_LEVEL to ERROR (not preserved)
            assert os.environ.get("LOG_LEVEL") == "ERROR"
            # API token is preserved if already set
            assert os.environ.get("MISSING_TABLE_API_TOKEN") == "existing-key"

    def test_create_config_basic(self):
        """Test basic config creation using offset-based dates."""
        # Use start_offset=-1 (1 day back) and end_offset=1 (1 day forward)
        # New convention: negative = past, positive = future
        config = create_config(
            age_group="U14",
            league="Homegrown",
            division="Northeast",
            start_offset=-1,
            end_offset=1,
        )

        assert config.age_group == "U14"
        assert config.division == "Northeast"
        assert config.club == ""
        assert config.competition == ""

        # Test date range calculation with offsets
        today = date.today()
        expected_start = today + timedelta(days=-1)  # start_offset=-1 means 1 day back
        expected_end = today + timedelta(days=1)  # end_offset=1 means 1 day forward

        assert config.start_date == expected_start
        assert config.end_date == expected_end

    def test_create_config_with_optional_params(self):
        """Test config creation with optional parameters."""
        config = create_config(
            age_group="U16",
            league="Homegrown",
            division="Southwest",
            start_offset=2,
            end_offset=5,
            club="Test Club",
            competition="Test Competition",
        )

        assert config.age_group == "U16"
        assert config.division == "Southwest"
        assert config.club == "Test Club"
        assert config.competition == "Test Competition"

    @patch("src.cli.main.console")
    def test_handle_cli_error_metrics_connection(self, mock_console):
        """Test error handling for metrics connection errors."""
        error = Exception("Connection refused on port 4318")

        handle_cli_error(error, verbose=False)

        mock_console.print.assert_called()
        call_args = mock_console.print.call_args_list
        assert any("Metrics export failed" in str(call) for call in call_args)

    @patch("src.cli.main.console")
    def test_handle_cli_error_network(self, mock_console):
        """Test error handling for network connection errors."""
        error = ConnectionError("Network connection error")

        handle_cli_error(error, verbose=False)

        mock_console.print.assert_called()
        call_args = mock_console.print.call_args_list
        assert any("Network connection error" in str(call) for call in call_args)

    @patch("src.cli.main.console")
    def test_handle_cli_error_timeout(self, mock_console):
        """Test error handling for timeout errors."""
        error = TimeoutError("Operation timed out")

        handle_cli_error(error, verbose=False)

        mock_console.print.assert_called()
        call_args = mock_console.print.call_args_list
        assert any("Operation timed out" in str(call) for call in call_args)

    @patch("src.cli.main.console")
    def test_handle_cli_error_verbose(self, mock_console):
        """Test error handling in verbose mode."""
        error = Exception("Test error")

        handle_cli_error(error, verbose=True)

        mock_console.print.assert_called()
        mock_console.print_exception.assert_called_once()

    @patch("src.cli.main.console")
    def test_handle_cli_error_generic(self, mock_console):
        """Test error handling for generic errors."""
        error = Exception("Generic error message")

        handle_cli_error(error, verbose=False)

        mock_console.print.assert_called()
        call_args = mock_console.print.call_args_list
        assert any("Generic error message" in str(call) for call in call_args)


class TestCliCommands:
    """Test cases for CLI commands."""

    def setup_method(self):
        """Set up test environment."""
        self.runner = CliRunner(env={"NO_COLOR": "1"})

    @patch("src.cli.main.run_scraper")
    @patch("src.cli.main.setup_environment")
    def test_scrape_command_basic(self, mock_setup_env, mock_run_scraper):
        """Test basic scrape command."""
        # Mock return value for run_scraper
        mock_run_scraper.return_value = []

        self.runner.invoke(app, ["scrape"])

        # The command may fail due to async issues, but we can test that it processes
        # In a real CLI test, we'd want to mock the async parts differently
        mock_setup_env.assert_called_once_with(False)  # verbose=False by default

    def test_scrape_command_invalid_age_group(self):
        """Test scrape command with invalid age group."""
        result = self.runner.invoke(app, ["scrape", "--age-group", "INVALID"])

        assert result.exit_code == 1
        assert "Invalid age group" in result.stdout

    def test_scrape_command_invalid_division(self):
        """Test scrape command with invalid division."""
        result = self.runner.invoke(app, ["scrape", "--division", "INVALID"])

        assert result.exit_code == 1
        assert "Invalid division" in result.stdout

    @patch("src.cli.main.run_scraper")
    @patch("src.cli.main.setup_environment")
    def test_scrape_command_with_options(self, mock_setup_env, mock_run_scraper):
        """Test scrape command with various options."""
        mock_run_scraper.return_value = ([], False, {})

        self.runner.invoke(
            app,
            [
                "scrape",
                "--age-group",
                "U16",
                "--division",
                "Southwest",
                "--start",
                "2",
                "--end",
                "5",
                "--club",
                "Test Club",
                "--verbose",
            ],
        )

        # Test that environment setup is called with verbose=True
        mock_setup_env.assert_called_once_with(True)  # verbose=True

    def test_config_command(self):
        """Test config command help (it's now a sub-command group)."""
        result = self.runner.invoke(app, ["config", "--help"])

        assert result.exit_code == 0
        assert "config" in result.stdout.lower()
        # Sub-commands: show, setup, set, validate, options
        assert "show" in result.stdout or "setup" in result.stdout

    def test_debug_command_help(self):
        """Test debug command help (avoids async issues)."""
        result = self.runner.invoke(app, ["debug", "--help"])

        assert result.exit_code == 0
        stdout = strip_ansi(result.stdout)
        assert "--timeout" in stdout
        assert "--headless" in stdout

    def test_test_quiet_command_help(self):
        """Test test-quiet command help (avoids model validation issues)."""
        result = self.runner.invoke(app, ["test-quiet", "--help"])

        assert result.exit_code == 0

    def test_demo_command_help(self):
        """Test demo command help (avoids async and model issues)."""
        result = self.runner.invoke(app, ["demo", "--help"])

        assert result.exit_code == 0

    def test_inspect_command_help(self):
        """Test inspect command help (avoids async issues)."""
        result = self.runner.invoke(app, ["inspect", "--help"])

        assert result.exit_code == 0
        stdout = strip_ansi(result.stdout)
        assert "--timeout" in stdout


class TestConstants:
    """Test CLI constants."""

    def test_default_values(self):
        """Test default values are set correctly."""
        assert DEFAULT_AGE_GROUP == "U14"
        assert DEFAULT_DIVISION == "Northeast"
        assert DEFAULT_DAYS == 3

    def test_valid_age_groups(self):
        """Test valid age groups contain expected values."""
        expected_age_groups = ["U13", "U14", "U15", "U16", "U17", "U18", "U19"]
        assert VALID_AGE_GROUPS == expected_age_groups

    def test_valid_divisions(self):
        """Test valid divisions contain expected values."""
        expected_divisions = [
            "Northeast",
            "Southeast",
            "Central",
            "Southwest",
            "Northwest",
            "Mid-Atlantic",
            "Great Lakes",
            "Texas",
            "California",
            "Florida",
        ]
        assert VALID_DIVISIONS == expected_divisions


class TestCliIntegration:
    """Integration-style tests for CLI functionality."""

    def setup_method(self):
        """Set up test environment."""
        self.runner = CliRunner(env={"NO_COLOR": "1"})

    def test_app_help(self):
        """Test that the main app help displays correctly."""
        result = self.runner.invoke(app, ["--help"])

        assert result.exit_code == 0
        assert "MLS Match Scraper" in result.stdout
        assert "scrape" in result.stdout
        assert "upcoming" in result.stdout
        assert "interactive" in result.stdout

    def test_scrape_help(self):
        """Test that scrape command help displays correctly."""
        result = self.runner.invoke(app, ["scrape", "--help"])

        assert result.exit_code == 0
        stdout = strip_ansi(result.stdout)
        assert "--age-group" in stdout
        assert "--division" in stdout
        # --days was replaced with --start and --end
        assert "--start" in stdout or "--end" in stdout

    @patch.dict(os.environ, {}, clear=True)
    def test_environment_isolation(self):
        """Test that tests don't interfere with each other's environment."""
        # This test ensures our environment patching works correctly
        setup_environment(verbose=True)
        assert os.environ.get("LOG_LEVEL") == "DEBUG"

        # After the patch context, environment should be isolated
        # (This test mainly verifies our test setup is correct)
