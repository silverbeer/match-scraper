"""Unit tests for environment configuration module."""

import os
from unittest.mock import patch

from src.cli.env_config import (
    OPTIONAL_ENV_VARS,
    REQUIRED_ENV_VARS,
    get_current_config,
    get_env_file_path,
    load_env_file,
    save_env_file,
    set_variable,
    validate_config,
)


class TestGetEnvFilePath:
    """Test getting the .env file path."""

    def test_get_env_file_path_with_pyproject(self, tmp_path):
        """Test finding .env file path when pyproject.toml exists."""
        # Create a temporary directory structure
        project_root = tmp_path / "project"
        project_root.mkdir()
        (project_root / "pyproject.toml").touch()

        # Create a subdirectory to test search upwards
        subdir = project_root / "src" / "cli"
        subdir.mkdir(parents=True)

        with patch("pathlib.Path.cwd", return_value=subdir):
            env_path = get_env_file_path()
            assert env_path == project_root / ".env"

    def test_get_env_file_path_fallback_to_cwd(self, tmp_path):
        """Test fallback to current directory when pyproject.toml not found."""
        # Create a directory without pyproject.toml
        test_dir = tmp_path / "test"
        test_dir.mkdir()

        with patch("pathlib.Path.cwd", return_value=test_dir):
            env_path = get_env_file_path()
            # Should fallback to current directory
            assert env_path == test_dir / ".env"


class TestLoadEnvFile:
    """Test loading environment variables from .env file."""

    def test_load_env_file_success(self, tmp_path):
        """Test successfully loading .env file."""
        env_file = tmp_path / ".env"
        env_content = """# Test env file
MISSING_TABLE_API_BASE_URL=https://api.test.com
MISSING_TABLE_API_TOKEN="test-token-123"
LOG_LEVEL=DEBUG
AGE_GROUP=U16
"""
        env_file.write_text(env_content)

        with patch("src.cli.env_config.get_env_file_path", return_value=env_file):
            env_vars = load_env_file()

        assert env_vars["MISSING_TABLE_API_BASE_URL"] == "https://api.test.com"
        assert env_vars["MISSING_TABLE_API_TOKEN"] == "test-token-123"
        assert env_vars["LOG_LEVEL"] == "DEBUG"
        assert env_vars["AGE_GROUP"] == "U16"

    def test_load_env_file_with_single_quotes(self, tmp_path):
        """Test loading .env file with single-quoted values."""
        env_file = tmp_path / ".env"
        env_content = "API_TOKEN='single-quoted-token'\n"
        env_file.write_text(env_content)

        with patch("src.cli.env_config.get_env_file_path", return_value=env_file):
            env_vars = load_env_file()

        assert env_vars["API_TOKEN"] == "single-quoted-token"

    def test_load_env_file_ignores_comments(self, tmp_path):
        """Test that comments are ignored."""
        env_file = tmp_path / ".env"
        env_content = """# This is a comment
VAR1=value1
# Another comment
VAR2=value2
"""
        env_file.write_text(env_content)

        with patch("src.cli.env_config.get_env_file_path", return_value=env_file):
            env_vars = load_env_file()

        assert len(env_vars) == 2
        assert env_vars["VAR1"] == "value1"
        assert env_vars["VAR2"] == "value2"

    def test_load_env_file_ignores_empty_lines(self, tmp_path):
        """Test that empty lines are ignored."""
        env_file = tmp_path / ".env"
        env_content = """VAR1=value1

VAR2=value2

"""
        env_file.write_text(env_content)

        with patch("src.cli.env_config.get_env_file_path", return_value=env_file):
            env_vars = load_env_file()

        assert len(env_vars) == 2

    def test_load_env_file_not_exists(self, tmp_path):
        """Test loading when .env file doesn't exist."""
        env_file = tmp_path / ".env"

        with patch("src.cli.env_config.get_env_file_path", return_value=env_file):
            env_vars = load_env_file()

        assert env_vars == {}

    def test_load_env_file_with_equals_in_value(self, tmp_path):
        """Test loading .env file with equals sign in value."""
        env_file = tmp_path / ".env"
        env_content = "CONNECTION_STRING=server=localhost;db=test\n"
        env_file.write_text(env_content)

        with patch("src.cli.env_config.get_env_file_path", return_value=env_file):
            env_vars = load_env_file()

        assert env_vars["CONNECTION_STRING"] == "server=localhost;db=test"

    def test_load_env_file_handles_read_error(self, tmp_path):
        """Test handling of file read errors."""
        env_file = tmp_path / ".env"
        env_file.touch()

        with patch("src.cli.env_config.get_env_file_path", return_value=env_file):
            with patch("builtins.open", side_effect=PermissionError("Access denied")):
                with patch("src.cli.env_config.console") as mock_console:
                    env_vars = load_env_file()
                    assert env_vars == {}
                    # Verify warning was printed
                    mock_console.print.assert_called_once()
                    assert "Warning: Could not read .env file" in str(
                        mock_console.print.call_args
                    )


class TestSaveEnvFile:
    """Test saving environment variables to .env file."""

    def test_save_env_file_success(self, tmp_path):
        """Test successfully saving .env file."""
        env_file = tmp_path / ".env"
        env_vars = {
            "MISSING_TABLE_API_BASE_URL": "https://api.test.com",
            "MISSING_TABLE_API_TOKEN": "test-token",
            "LOG_LEVEL": "DEBUG",
        }

        with patch("src.cli.env_config.get_env_file_path", return_value=env_file):
            result = save_env_file(env_vars)

        assert result is True
        assert env_file.exists()

        # Verify content
        content = env_file.read_text()
        assert "MISSING_TABLE_API_BASE_URL=https://api.test.com" in content
        assert "MISSING_TABLE_API_TOKEN=test-token" in content
        assert "LOG_LEVEL=DEBUG" in content
        assert "# MLS Match Scraper Environment Configuration" in content

    def test_save_env_file_creates_directory(self, tmp_path):
        """Test that save_env_file creates parent directories if needed."""
        env_file = tmp_path / "config" / "subdir" / ".env"
        env_vars = {"VAR1": "value1"}

        with patch("src.cli.env_config.get_env_file_path", return_value=env_file):
            result = save_env_file(env_vars)

        assert result is True
        assert env_file.exists()
        assert env_file.parent.exists()

    def test_save_env_file_handles_write_error(self, tmp_path):
        """Test handling of file write errors."""
        env_file = tmp_path / ".env"
        env_vars = {"VAR1": "value1"}

        with patch("src.cli.env_config.get_env_file_path", return_value=env_file):
            with patch("builtins.open", side_effect=PermissionError("Access denied")):
                with patch("src.cli.env_config.console") as mock_console:
                    result = save_env_file(env_vars)
                    assert result is False
                    # Verify error was printed
                    mock_console.print.assert_called_once()
                    assert "Error saving .env file" in str(mock_console.print.call_args)


class TestGetCurrentConfig:
    """Test getting current configuration."""

    def test_get_current_config_from_env_vars(self):
        """Test getting config when variables are in environment."""
        env_vars = {
            "MISSING_TABLE_API_BASE_URL": "https://api.test.com",
            "MISSING_TABLE_API_TOKEN": "token123",
            "LOG_LEVEL": "DEBUG",
            "AGE_GROUP": "U16",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            with patch("src.cli.env_config.load_env_file", return_value={}):
                required, optional = get_current_config()

        assert required["MISSING_TABLE_API_BASE_URL"] == "https://api.test.com"
        assert required["MISSING_TABLE_API_TOKEN"] == "token123"
        assert optional["LOG_LEVEL"] == "DEBUG"
        assert optional["AGE_GROUP"] == "U16"

    def test_get_current_config_from_env_file(self):
        """Test getting config from .env file when not in environment."""
        env_file_vars = {
            "MISSING_TABLE_API_BASE_URL": "https://file.api.com",
            "MISSING_TABLE_API_TOKEN": "file-token",
            "LOG_LEVEL": "INFO",
        }

        with patch.dict(os.environ, {}, clear=True):
            with patch("src.cli.env_config.load_env_file", return_value=env_file_vars):
                required, optional = get_current_config()

        assert required["MISSING_TABLE_API_BASE_URL"] == "https://file.api.com"
        assert required["MISSING_TABLE_API_TOKEN"] == "file-token"
        assert optional["LOG_LEVEL"] == "INFO"

    def test_get_current_config_env_takes_precedence(self):
        """Test that environment variables take precedence over .env file."""
        env_file_vars = {
            "MISSING_TABLE_API_BASE_URL": "https://file.api.com",
        }
        env_vars = {
            "MISSING_TABLE_API_BASE_URL": "https://env.api.com",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            with patch("src.cli.env_config.load_env_file", return_value=env_file_vars):
                required, optional = get_current_config()

        assert required["MISSING_TABLE_API_BASE_URL"] == "https://env.api.com"

    def test_get_current_config_uses_defaults(self):
        """Test that defaults are used for optional variables."""
        with patch.dict(os.environ, {}, clear=True):
            with patch("src.cli.env_config.load_env_file", return_value={}):
                required, optional = get_current_config()

        # Optional variables should have their defaults
        assert optional["LOG_LEVEL"] == "WARNING"
        assert optional["AGE_GROUP"] == "U14"
        assert optional["DIVISION"] == "Northeast"
        assert optional["LOOK_BACK_DAYS"] == "3"

    def test_get_current_config_missing_required(self):
        """Test getting config when required variables are missing."""
        with patch.dict(os.environ, {}, clear=True):
            with patch("src.cli.env_config.load_env_file", return_value={}):
                required, optional = get_current_config()

        # Required variables should be None when missing
        assert required["MISSING_TABLE_API_BASE_URL"] is None
        assert required["MISSING_TABLE_API_TOKEN"] is None


class TestSetVariable:
    """Test setting environment variables."""

    def test_set_variable_success(self, tmp_path):
        """Test successfully setting a variable."""
        env_file = tmp_path / ".env"
        existing_vars = {"VAR1": "value1"}

        with patch("src.cli.env_config.get_env_file_path", return_value=env_file):
            with patch("src.cli.env_config.load_env_file", return_value=existing_vars):
                with patch(
                    "src.cli.env_config.save_env_file", return_value=True
                ) as mock_save:
                    with patch("src.cli.env_config.console"):
                        result = set_variable("LOG_LEVEL", "DEBUG")

        assert result is True
        # Verify save was called with updated vars
        called_vars = mock_save.call_args[0][0]
        assert called_vars["LOG_LEVEL"] == "DEBUG"
        assert called_vars["VAR1"] == "value1"

    def test_set_variable_invalid_name(self):
        """Test setting an invalid variable name."""
        with patch("src.cli.env_config.console") as mock_console:
            result = set_variable("INVALID_VAR", "value")

        assert result is False
        # Verify error message was printed
        mock_console.print.assert_called()
        assert "Unknown variable" in str(mock_console.print.call_args_list[0])

    def test_set_variable_invalid_choice(self):
        """Test setting a variable with an invalid choice."""
        with patch("src.cli.env_config.console") as mock_console:
            result = set_variable("LOG_LEVEL", "INVALID")

        assert result is False
        # Verify error message was printed
        assert "Invalid value" in str(mock_console.print.call_args_list[0])

    def test_set_variable_valid_choice(self, tmp_path):
        """Test setting a variable with a valid choice."""
        env_file = tmp_path / ".env"

        with patch("src.cli.env_config.get_env_file_path", return_value=env_file):
            with patch("src.cli.env_config.load_env_file", return_value={}):
                with patch("src.cli.env_config.save_env_file", return_value=True):
                    with patch("src.cli.env_config.console"):
                        result = set_variable("AGE_GROUP", "U16")

        assert result is True

    def test_set_variable_save_failure(self, tmp_path):
        """Test handling save failure."""
        env_file = tmp_path / ".env"

        with patch("src.cli.env_config.get_env_file_path", return_value=env_file):
            with patch("src.cli.env_config.load_env_file", return_value={}):
                with patch("src.cli.env_config.save_env_file", return_value=False):
                    with patch("src.cli.env_config.console") as mock_console:
                        result = set_variable("LOG_LEVEL", "INFO")

        assert result is False
        # Verify error message
        assert "Failed to set" in str(mock_console.print.call_args_list[-1])


class TestValidateConfig:
    """Test configuration validation."""

    def test_validate_config_all_required_set(self):
        """Test validation when all required variables are set."""
        required_config = {
            "MISSING_TABLE_API_BASE_URL": "https://api.test.com",
            "MISSING_TABLE_API_TOKEN": "token123",
        }
        optional_config = {}

        with patch(
            "src.cli.env_config.get_current_config",
            return_value=(required_config, optional_config),
        ):
            with patch("src.cli.env_config.console") as mock_console:
                result = validate_config()

        assert result is True
        # Verify success message
        assert "All required environment variables are configured" in str(
            mock_console.print.call_args
        )

    def test_validate_config_missing_required(self):
        """Test validation when required variables are missing."""
        required_config = {
            "MISSING_TABLE_API_BASE_URL": None,
            "MISSING_TABLE_API_TOKEN": None,
        }
        optional_config = {}

        with patch(
            "src.cli.env_config.get_current_config",
            return_value=(required_config, optional_config),
        ):
            with patch("src.cli.env_config.console") as mock_console:
                result = validate_config()

        assert result is False
        # Verify error messages were printed
        print_calls = [str(call) for call in mock_console.print.call_args_list]
        assert any(
            "Missing required environment variables" in call for call in print_calls
        )
        assert any("MISSING_TABLE_API_BASE_URL" in call for call in print_calls)
        assert any("MISSING_TABLE_API_TOKEN" in call for call in print_calls)

    def test_validate_config_some_missing(self):
        """Test validation when some required variables are missing."""
        required_config = {
            "MISSING_TABLE_API_BASE_URL": "https://api.test.com",
            "MISSING_TABLE_API_TOKEN": None,
        }
        optional_config = {}

        with patch(
            "src.cli.env_config.get_current_config",
            return_value=(required_config, optional_config),
        ):
            with patch("src.cli.env_config.console") as mock_console:
                result = validate_config()

        assert result is False
        # Verify error messages
        print_calls = [str(call) for call in mock_console.print.call_args_list]
        assert any(
            "Missing required environment variables" in call for call in print_calls
        )
        assert any("MISSING_TABLE_API_TOKEN" in call for call in print_calls)


class TestConstants:
    """Test configuration constants."""

    def test_required_env_vars_structure(self):
        """Test that required env vars are properly structured."""
        assert "MISSING_TABLE_API_BASE_URL" in REQUIRED_ENV_VARS
        assert "MISSING_TABLE_API_TOKEN" in REQUIRED_ENV_VARS

        # Check structure
        for _var_name, var_info in REQUIRED_ENV_VARS.items():
            assert "description" in var_info
            assert "default" in var_info
            assert "example" in var_info

    def test_optional_env_vars_structure(self):
        """Test that optional env vars are properly structured."""
        assert "LOG_LEVEL" in OPTIONAL_ENV_VARS
        assert "AGE_GROUP" in OPTIONAL_ENV_VARS
        assert "DIVISION" in OPTIONAL_ENV_VARS
        assert "LOOK_BACK_DAYS" in OPTIONAL_ENV_VARS

        # Check structure
        for _var_name, var_info in OPTIONAL_ENV_VARS.items():
            assert "description" in var_info
            assert "default" in var_info

    def test_optional_vars_with_choices(self):
        """Test that optional vars with choices have valid defaults."""
        for _var_name, var_info in OPTIONAL_ENV_VARS.items():
            if "choices" in var_info:
                # Default should be in choices
                assert var_info["default"] in var_info["choices"]
