# Match Scraper

[![Tests](https://github.com/silverbeer/match-scraper/actions/workflows/test-and-publish.yml/badge.svg)](https://github.com/silverbeer/match-scraper/actions/workflows/test-and-publish.yml)
[![Coverage](https://img.shields.io/badge/coverage-25.2%25-green)](https://silverbeer.github.io/match-scraper/)
[![Python](https://img.shields.io/badge/python-3.13%2B-blue)](https://python.org)
[![Code style: Ruff](https://img.shields.io/badge/code%20style-ruff-black)](https://github.com/astral-sh/ruff)
[![Powered by uv](https://img.shields.io/badge/powered%20by-uv-blue)](https://github.com/astral-sh/uv)

🏆 **[View Test Reports & Coverage](https://silverbeer.github.io/match-scraper/)**

Automated soccer match data scraper with RabbitMQ queue integration.

## Overview

This application scrapes match data from youth soccer websites and sends it to a RabbitMQ queue for processing by backend workers. Deployed on Google Kubernetes Engine (GKE) as a scheduled CronJob, built with Playwright and comprehensive monitoring.

## 📚 Documentation

**[📖 Full Documentation →](docs/README.md)**

Quick links:
- **[CLI Usage Guide](docs/guides/cli-usage.md)** - Complete CLI reference and examples
- **[GKE Deployment](docs/deployment/gke-deployment.md)** - Kubernetes deployment guide
- **[Testing Guide](docs/development/testing.md)** - Unit, integration, and E2E tests
- **[Observability Setup](docs/observability/grafana-cloud-setup.md)** - Metrics and logging with Grafana Cloud

Browse all documentation in the **[docs/](docs/)** folder, organized by topic.

## Features

- **Automated Scraping**: Playwright-based web scraping of youth soccer match data
- **Queue Integration**: RabbitMQ message queue for reliable async processing
- **Scheduled Execution**: Kubernetes CronJob runs daily at 6 AM UTC
- **Containerized Deployment**: GKE deployment with optimized Docker container
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

## Logging and Monitoring

### Structured Logging
The application uses structured logging with Pydantic model support:

```python
from src.utils import get_logger

logger = get_logger()
logger.info("Operation completed", extra={"operation": "scraping", "match": match})
```

### Metrics Collection
OpenTelemetry metrics are available for monitoring:

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

# OpenTelemetry Metrics (optional)
OTEL_EXPORTER_OTLP_ENDPOINT=https://otlp-gateway.grafana.net
OTEL_EXPORTER_OTLP_HEADERS=Authorization=Bearer <your-token>
OTEL_METRIC_EXPORT_INTERVAL=5000
OTEL_METRIC_EXPORT_TIMEOUT=30000
```

## Configuration

The scraper uses environment variables for configuration. See `src/scraper/config.py` for available options:

- `BASE_URL`: Base URL for the soccer website
- `RABBITMQ_URL`: RabbitMQ connection URL (e.g., "amqp://user:pass@host:5672/")
- `QUEUE_NAME`: Queue name for match data (default: "matches")
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
│   ├── filter_application.py # Website filter interactions
│   ├── match_extraction.py # Match data extraction
│   ├── mls_scraper.py     # Main scraper orchestration
│   └── models.py          # Pydantic data models
├── utils/
│   ├── logger.py          # Structured logging
│   ├── metrics.py         # OpenTelemetry metrics
│   └── example_usage.py   # Usage examples
tests/
├── unit/                  # Fast unit tests (CI)
├── integration/           # Multi-component tests
├── e2e/                  # End-to-end browser tests
k8s/                      # Kubernetes manifests (GKE)
├── namespace.yaml         # Kubernetes namespace
├── configmap.yaml         # Configuration
├── secret.yaml           # Credentials
└── cronjob.yaml          # Scheduled job
k3s/                      # K3s/local manifests
├── rabbitmq/             # RabbitMQ deployment
│   ├── namespace.yaml    # Shared namespace
│   ├── statefulset.yaml  # RabbitMQ StatefulSet
│   ├── service.yaml      # Internal and NodePort services
│   ├── configmap.yaml    # RabbitMQ configuration
│   └── secret.yaml       # RabbitMQ credentials
└── match-scraper/        # Match-scraper deployment
    ├── configmap.yaml    # Scraper configuration
    ├── secret.yaml       # API tokens (optional)
    └── cronjob.yaml      # Scheduled job
scripts/
├── deploy-gke-complete.sh # Complete GKE deployment
├── deploy-gke-env.sh     # Environment-based deployment
├── build-and-push-gke.sh # Container build and push
├── deploy-to-gke.sh      # Kubernetes deployment
├── test-gke.sh           # GKE testing and monitoring
├── deploy-k3s.sh         # K3s local deployment
├── test-k3s.sh           # K3s testing and monitoring
└── test-review.py        # Test analysis helper script
```

## Deployment

### Google Kubernetes Engine (GKE)

The scraper is deployed as a Kubernetes CronJob on GKE, running daily at 6 AM UTC.

#### Quick Start

Deploy with a single command:

```bash
# Automated deployment (recommended)
./scripts/deploy-gke-complete.sh
```

This script will:
1. ✅ Check prerequisites (gcloud, kubectl, docker)
2. ✅ Load configuration from terraform/dev.tfvars
3. ✅ Build and push Docker image to GCP Container Registry
4. ✅ Deploy Kubernetes manifests (CronJob, ConfigMap, Secret)
5. ✅ Test the deployment with a manual job
6. ✅ Display deployment summary and management commands

#### Alternative: Using .env.dev file

```bash
# Create environment file
cp env.dev.template .env.dev
# Edit .env.dev with your values

# Deploy using environment file
./scripts/deploy-gke-env.sh .env.dev
```

#### Manual Deployment

For manual deployments:

```bash
# Build and push container
./scripts/build-and-push-gke.sh YOUR_PROJECT_ID

# Deploy to GKE
./scripts/deploy-to-gke.sh YOUR_PROJECT_ID YOUR_API_TOKEN

# Test the deployment
./scripts/test-gke.sh trigger
./scripts/test-gke.sh logs
```

**Documentation:**
- 📖 [GKE Deployment Guide](docs/deployment/gke-deployment.md) - Complete GKE deployment guide
- 🧪 [Testing Guide](docs/deployment/gke-testing.md) - Testing and monitoring guide
- 🚀 [Migration Guide](docs/deployment/migration-to-gke.md) - Migration from AWS Lambda

**Infrastructure Features:**
- Kubernetes CronJob with configurable schedule
- GCP Container Registry for container images
- ConfigMap for non-sensitive configuration
- Kubernetes Secret for API tokens
- Resource requests and limits for GKE Autopilot
- Comprehensive testing and monitoring scripts

### K3s/Rancher Local Deployment

For local/cost-effective deployments, run match-scraper with RabbitMQ in k3s:

#### Quick Start

```bash
# One-command deployment (RabbitMQ + match-scraper)
./scripts/deploy-k3s.sh

# Test the pipeline
./scripts/test-k3s.sh trigger
./scripts/test-k3s.sh logs

# Check RabbitMQ status
./scripts/test-k3s.sh rabbitmq
```

**Architecture:**
```
match-scraper (CronJob) → RabbitMQ → backend workers → database
```

**Benefits:**
- ✅ No cloud costs
- ✅ Same queue-based architecture
- ✅ Full local control
- ✅ Easy dev/prod environment switching

**Documentation:**
- 📖 [K3s Deployment Guide](docs/deployment/k3s-deployment.md) - Complete local deployment guide
- 🔧 [Configuration](k3s/match-scraper/configmap.yaml) - Scraper configuration
- 🐰 [RabbitMQ Setup](k3s/rabbitmq/) - RabbitMQ manifests

**Key Features:**
- RabbitMQ StatefulSet with persistent storage
- Management UI at http://localhost:30672
- Automated build and image import to k3s
- Manual job triggering for testing
- Real-time log monitoring

## CLI Tool

The project includes **mls-scraper**, a beautiful command-line interface for scraping and displaying youth soccer match data:

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
