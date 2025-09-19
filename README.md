# MLS Match Scraper

Automated MLS match data scraper for missing-table.com API integration.

## Overview

This serverless application scrapes match data from the MLS Next website and posts it to the missing-table.com API. Built with AWS Lambda, Playwright, and comprehensive monitoring using AWS Powertools and OpenTelemetry.

## Features

- **Automated Scraping**: Playwright-based web scraping of MLS Next match data
- **API Integration**: Direct posting to missing-table.com API
- **Comprehensive Monitoring**: Structured logging with AWS Powertools and metrics with OpenTelemetry
- **Serverless Architecture**: AWS Lambda deployment with Terraform infrastructure
- **Data Validation**: Pydantic models for robust data validation and serialization
- **High Test Coverage**: 91.57% test coverage with comprehensive unit tests

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

### Coverage Requirements
- Minimum coverage: 50%
- Current coverage: 91.57%
- Coverage reports available in `htmlcov/` directory

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
    match_date=datetime.now(),
    age_group="U14",
    division="Northeast",
    status="scheduled"
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
├── scraper/
│   ├── config.py          # Configuration management
│   └── models.py          # Data models
├── utils/
│   ├── logger.py          # AWS Powertools logging
│   ├── metrics.py         # OpenTelemetry metrics
│   └── example_usage.py   # Usage examples
tests/
├── unit/
│   ├── test_config.py     # Configuration tests
│   ├── test_models.py     # Model tests
│   ├── test_logger.py     # Logging tests
│   └── test_metrics.py    # Metrics tests
```

## Deployment

Infrastructure is managed with Terraform. See the `terraform/` directory for deployment configuration.

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

# Run pre-commit hooks
uv run pre-commit run --all-files
```
