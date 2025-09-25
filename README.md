# MLS Match Scraper

[![Tests](https://github.com/silverbeer/match-scraper/actions/workflows/test-and-publish.yml/badge.svg)](https://github.com/silverbeer/match-scraper/actions/workflows/test-and-publish.yml)
[![Coverage](https://img.shields.io/badge/coverage-25.2%25-green)](https://silverbeer.github.io/match-scraper/)
[![Python](https://img.shields.io/badge/python-3.13%2B-blue)](https://python.org)
[![Code style: Ruff](https://img.shields.io/badge/code%20style-ruff-black)](https://github.com/astral-sh/ruff)
[![Powered by uv](https://img.shields.io/badge/powered%20by-uv-blue)](https://github.com/astral-sh/uv)

🏆 **[View Test Reports & Coverage](https://silverbeer.github.io/match-scraper/)**

Automated MLS match data scraper for missing-table.com API integration.

## Overview

This serverless application scrapes match data from the MLS Next website and posts it to the missing-table.com API. Built with AWS Lambda, Playwright, and comprehensive monitoring using AWS Powertools and OpenTelemetry.

## Features

- **Automated Scraping**: Playwright-based web scraping of MLS Next match data
- **API Integration**: Direct posting to missing-table.com API
- **Comprehensive Monitoring**: Structured logging with AWS Powertools and metrics with OpenTelemetry
- **Serverless Architecture**: AWS Lambda deployment with Terraform infrastructure
- **Data Validation**: Pydantic models for robust data validation and serialization
- **Quality Testing**: Comprehensive test suite with unit, integration, and e2e tests

## Development Setup

1. Install dependencies:
   ```bash
   uv sync --all-groups
   ```

2. Install pre-commit hooks:
   ```bash
   uv run pre-commit install
   ```

## Testing

### Run All Tests
```bash
uv run pytest
```

### Run Tests with Coverage
```bash
uv run pytest --cov=src --cov-report=term-missing
```

### Run Specific Test Categories
```bash
# Unit tests only
uv run pytest tests/unit/ -v

# Run with coverage and HTML report
uv run pytest --cov=src --cov-report=html --cov-report=term-missing

# Run specific test files
uv run pytest tests/unit/test_logger.py tests/unit/test_metrics.py -v
```

### Test Structure
- `tests/unit/` - Fast unit tests (run on every commit)
- `tests/integration/` - Multi-component integration tests
- `tests/e2e/` - End-to-end browser automation tests
- Coverage reports available in GitHub Pages

## Data Models

### Pydantic Models
The application uses Pydantic v2 for data validation and serialization:

```python
from src.scraper.models import Match, ScrapingMetrics
from datetime import datetime

# Create a match with automatic validation
match = Match(
    match_id="12345",
    home_team="Team A",
    away_team="Team B",
    match_datetime=datetime.now(),
    # Note: age_group, division, and status are computed/computed fields
)

# Serialize to JSON
match_json = match.model_dump_json()

# Validate data automatically
metrics = ScrapingMetrics(
    games_scheduled=5,
    games_scored=3,
    api_calls_successful=10,
    api_calls_failed=0,
    execution_duration_ms=1500,
    errors_encountered=0
)
```

## Logging and Metrics

### Structured Logging
The application uses AWS Powertools for structured JSON logging with Pydantic model support:

```python
from src.utils import get_logger

logger = get_logger()
logger.info("Operation completed", extra={"operation": "scraping", "match": match})
```

### Metrics Collection
OpenTelemetry metrics are exported to Grafana Cloud via OTLP:

```python
from src.utils import get_metrics

metrics = get_metrics()
metrics.record_games_scheduled(5, {"age_group": "U14"})

# Time operations
with metrics.time_operation("scraping"):
    # Your code here
    pass
```

### Environment Variables for Observability
```bash
# Logging
LOG_LEVEL=INFO

# OpenTelemetry Metrics
OTEL_EXPORTER_OTLP_ENDPOINT=https://otlp-gateway.grafana.net
OTEL_EXPORTER_OTLP_HEADERS=Authorization=Bearer <your-token>
OTEL_METRIC_EXPORT_INTERVAL=5000
OTEL_METRIC_EXPORT_TIMEOUT=30000
```

## Configuration

The scraper uses environment variables for configuration. See `src/scraper/config.py` for available options:

- `MLS_BASE_URL`: Base URL for MLS Next website
- `API_BASE_URL`: Base URL for missing-table.com API
- `API_KEY`: Authentication key for missing-table.com API
- `DEFAULT_AGE_GROUP`: Default age group to scrape (e.g., "U14")
- `DEFAULT_DIVISION`: Default division to scrape (e.g., "Northeast")
- `DEFAULT_LOOK_BACK_DAYS`: Number of days to look back for matches

## Project Structure

```
src/
├── cli/
│   └── main.py            # CLI interface with Typer
├── scraper/
│   ├── browser.py         # Playwright browser management
│   ├── calendar_interaction.py # Calendar widget handling
│   ├── config.py          # Configuration management
│   ├── consent_handler.py # Cookie consent handling
│   ├── filter_application.py # MLS filter interactions
│   ├── match_extraction.py # Match data extraction
│   ├── mls_scraper.py     # Main scraper orchestration
│   └── models.py          # Pydantic data models
├── utils/
│   ├── logger.py          # AWS Powertools logging
│   ├── metrics.py         # OpenTelemetry metrics
│   └── example_usage.py   # Usage examples
tests/
├── unit/                  # Fast unit tests (CI)
├── integration/           # Multi-component tests
├── e2e/                  # End-to-end browser tests
.claude/
├── agents/
│   └── test-guardian.md   # Test Guardian agent config
└── README.md             # Agent documentation
scripts/
└── test-review.py        # Test analysis helper script
```

## Deployment

Infrastructure is managed with Terraform. See the `terraform/` directory for deployment configuration.

## CLI Tool

The project includes **mls-scraper**, a beautiful command-line interface for scraping and displaying MLS match data:

```bash
# Basic scraping with rich formatting
uv run mls-scraper scrape

# Scrape specific age group and division
uv run mls-scraper scrape --age-group U16 --division Southwest

# Show upcoming games in clean format
uv run mls-scraper upcoming

# Interactive mode with guided configuration
uv run mls-scraper interactive

# Quiet output perfect for scripting
uv run mls-scraper scrape --quiet

# Debug mode for troubleshooting
uv run mls-scraper debug

# Show all configuration options
uv run mls-scraper config
```

### CLI Features

- **Rich Formatting**: Beautiful tables with colors and statistics
- **Multiple Output Modes**: Rich display for humans, quiet mode for scripts
- **Interactive Mode**: Guided experience for exploring match data
- **Debug Tools**: Step-by-step troubleshooting and page inspection
- **Flexible Filtering**: Age group, division, club, and competition filters
- **Smart Date Handling**: Automatic date ranges and upcoming game detection

## Development Tools

### 🤖 Test Guardian Agent
Specialized AI agent for automated test review, creation, and debugging.

```bash
# In Claude Code, activate the agent:
/agents test-guardian

# Or use the helper script:
uv run python scripts/test-review.py review
```

**Capabilities:**
- Review code changes for missing test coverage
- Generate comprehensive unit tests following project patterns
- Debug and fix async mock issues (Playwright, AsyncMock)
- Update tests when models or APIs change

**Usage Examples:**
- `"Review recent commits and identify test coverage gaps"`
- `"Fix the failing tests in test_match_extraction.py"`
- `"Create comprehensive tests for the new scraping module"`

See [`.claude/README.md`](.claude/README.md) for detailed agent documentation.

## Development Commands

```bash
# Install dependencies
uv sync --all-groups

# Run linting
uv run ruff check src tests

# Run type checking
uv run mypy src

# Run tests with coverage
uv run pytest --cov=src --cov-report=term-missing

# Quick test review (shows recent changes + test status)
uv run python scripts/test-review.py review

# Run pre-commit hooks
uv run pre-commit run --all-files
```
