# 📚 MLS Match Scraper Documentation

Welcome to the documentation for the MLS Match Scraper library. This library provides the core scraping engine used by [match-scraper-agent](https://github.com/silverbeer/match-scraper-agent) for production deployment.

> **Deployment Note:** CronJob scheduling, Docker builds, and K3s manifests are managed in the [match-scraper-agent](https://github.com/silverbeer/match-scraper-agent) repo. Deployment docs here are kept for historical reference.

## 📖 Quick Navigation

### 🚀 Getting Started
- [Main README](../README.md) - Project overview, features, and quick start
- [CLI Usage Guide](guides/cli-usage.md) - Complete guide to using the command-line interface

### 🛠️ Development
- [Testing Guide](development/testing.md) - Unit, integration, and E2E testing
- [E2E Testing](development/e2e-testing.md) - End-to-end browser automation tests
- [Coverage Guide](development/coverage.md) - Code coverage setup and reporting
- [Test Reports Access](development/test-reports-access.md) - Accessing test reports and coverage
- [Fast Commits](development/fast-commits.md) - Tips for faster development workflow

### 🚢 Deployment
- [K3s Deployment Guide](deployment/k3s-deployment.md) - Historical reference (deployment now in [match-scraper-agent](https://github.com/silverbeer/match-scraper-agent))
- [Supabase Credentials Guide](deployment/supabase-credentials.md) - How to get Supabase credentials for production

### 📊 Observability
- [Grafana Cloud Setup](observability/grafana-cloud-setup.md) - Metrics and logs with Grafana Cloud
- [Fix Loki Auth](observability/fix-loki-auth.md) - Troubleshooting Loki authentication
- [Observability Review](observability/observability-review.md) - Observability implementation review
- [Observability Success](observability/observability-success.md) - Successful observability setup

### 🏗️ Architecture
- [Async Message Queue Architecture](architecture/async-message-queue-architecture.md) - **⭐ Educational guide to the complete pipeline** (match-scraper → RabbitMQ → Celery → Supabase)
- [RabbitMQ Fanout Pattern: Dev/Prod](architecture/rabbitmq-fanout-dev-prod.md) - **NEW** Fanout exchange pattern for environment separation
- [Fix Summary](architecture/fix-summary.md) - Summary of architectural fixes and improvements

### 📘 Guides
- [CLI Usage Guide](guides/cli-usage.md) - Complete guide to using the command-line interface
- [Database Fix Guide](guides/database-fix.md) - Troubleshooting database issues
- [RabbitMQ Password Change](guides/rabbitmq-password-change.md) - How to change RabbitMQ password in k3s deployment

## 🗂️ Documentation Structure

```
docs/
├── README.md                    # This file - documentation hub
├── guides/                      # How-to guides and tutorials
│   ├── cli-usage.md            # CLI usage and examples
│   ├── database-fix.md         # Database troubleshooting
│   └── rabbitmq-password-change.md  # RabbitMQ password change guide
├── development/                 # Development guides
│   ├── testing.md              # Testing strategies
│   ├── e2e-testing.md          # E2E test setup
│   ├── coverage.md             # Coverage reporting
│   ├── test-reports-access.md  # Accessing test results
│   └── fast-commits.md         # Development workflow tips
├── deployment/                  # Deployment guides
│   ├── k3s-deployment.md       # K3s local deployment
│   └── supabase-credentials.md # Getting Supabase credentials
├── observability/               # Monitoring and logging
│   ├── grafana-cloud-setup.md  # Grafana Cloud integration
│   ├── fix-loki-auth.md        # Loki troubleshooting
│   ├── observability-review.md # Implementation review
│   └── observability-success.md # Success metrics
└── architecture/                # Architecture decisions
    ├── async-message-queue-architecture.md  # Complete pipeline guide
    ├── rabbitmq-fanout-dev-prod.md         # Dev/prod environment separation
    └── fix-summary.md          # Architectural improvements
```

## 🎯 Documentation by Role

### I'm a Developer
1. Start with [Testing Guide](development/testing.md)
2. Review [Coverage Guide](development/coverage.md)
3. Check [Fast Commits](development/fast-commits.md) for productivity tips
4. Use [CLI Usage Guide](guides/cli-usage.md) for local testing

### I'm a DevOps Engineer
1. For deployment: See [match-scraper-agent](https://github.com/silverbeer/match-scraper-agent) (owns CronJobs and K3s manifests)
2. Historical reference: [K3s Deployment Guide](deployment/k3s-deployment.md)
3. Set up [Grafana Cloud Setup](observability/grafana-cloud-setup.md)

### I'm New to the Project
1. Start with the [Main README](../README.md)
2. **Understand the architecture**: [Async Message Queue Architecture](architecture/async-message-queue-architecture.md)
3. Read [CLI Usage Guide](guides/cli-usage.md)
4. Try the CLI: `uv run mls-scraper demo`
5. Review [Testing Guide](development/testing.md)

### I'm Troubleshooting Issues
1. Check [Database Fix Guide](guides/database-fix.md)
2. Review [Fix Loki Auth](observability/fix-loki-auth.md)
3. [RabbitMQ Password Change](guides/rabbitmq-password-change.md) for security warnings or password updates

## 🔍 Finding Documentation

### By Topic
- **Architecture**:
  - [`architecture/async-message-queue-architecture.md`](architecture/async-message-queue-architecture.md) ⭐ Start here!
  - [`architecture/rabbitmq-fanout-dev-prod.md`](architecture/rabbitmq-fanout-dev-prod.md) - Dev/prod environment setup
- **CLI & Tools**: [`guides/cli-usage.md`](guides/cli-usage.md)
- **Testing**: [`development/testing.md`](development/testing.md), [`development/e2e-testing.md`](development/e2e-testing.md)
- **Deployment**: [`deployment/k3s-deployment.md`](deployment/k3s-deployment.md)
- **Monitoring**: [`observability/grafana-cloud-setup.md`](observability/grafana-cloud-setup.md)

### By Task
- **Understanding the Pipeline**: [`architecture/async-message-queue-architecture.md`](architecture/async-message-queue-architecture.md) ⭐
- **Running Tests**: [`development/testing.md`](development/testing.md)
- **Deploying Locally (k3s)**: See [match-scraper-agent](https://github.com/silverbeer/match-scraper-agent) (historical ref: [`deployment/k3s-deployment.md`](deployment/k3s-deployment.md))
- **Setting up Monitoring**: [`observability/grafana-cloud-setup.md`](observability/grafana-cloud-setup.md)
- **Using the CLI**: [`guides/cli-usage.md`](guides/cli-usage.md)
- **Changing RabbitMQ Password**: [`guides/rabbitmq-password-change.md`](guides/rabbitmq-password-change.md)
- **Fixing Issues**: [`guides/database-fix.md`](guides/database-fix.md)

## 📝 Contributing to Documentation

When working on this project, please keep documentation up-to-date:

1. **New Features**: Update relevant guides in `docs/guides/`
2. **Architecture Changes**: Document in `docs/architecture/`
3. **Deployment Changes**: Update `docs/deployment/`
4. **Testing Changes**: Update `docs/development/`
5. **Observability Changes**: Update `docs/observability/`

See [CLAUDE.md](../CLAUDE.md) for AI assistant guidelines on maintaining documentation.

## 🔗 External Resources

- [Project Repository](https://github.com/silverbeer/match-scraper)
- [Test Reports & Coverage](https://silverbeer.github.io/match-scraper/)
- [Grafana Cloud](https://grafana.com/)
## 📧 Getting Help

- Check documentation in this folder first
- Review [GitHub Issues](https://github.com/silverbeer/match-scraper/issues)
- See the [Main README](../README.md) for project overview

---

**Last Updated**: 2026-03-05

This documentation is maintained alongside the codebase. If you find outdated information, please update it and include the changes in your pull request.
