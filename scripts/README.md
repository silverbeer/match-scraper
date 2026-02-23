# Scripts Directory

Utility scripts for the MLS Match Scraper project.

## Deployment

**`deploy-k3s.sh`** - Deploy match-scraper and RabbitMQ to local K3s cluster

```bash
./scripts/deploy-k3s.sh                    # Full deployment (scraper + RabbitMQ)
./scripts/deploy-k3s.sh --deploy-workers   # Full deployment + Celery workers
./scripts/deploy-k3s.sh --skip-build       # Skip Docker build
./scripts/deploy-k3s.sh --rabbitmq-only    # Deploy only RabbitMQ
./scripts/deploy-k3s.sh --scraper-only     # Deploy only match-scraper
```

**`deploy-grafana-dashboards.sh`** - Deploy Grafana dashboards

```bash
./scripts/deploy-grafana-dashboards.sh
```

## Testing

**`trigger-scrape.sh`** - Manually trigger a scrape job

```bash
./scripts/trigger-scrape.sh
```

**`test-k3s.sh`** - Test K3s deployment

```bash
./scripts/test-k3s.sh
```

**`smoke_test_stderr_formatter.py`** - Verify stderr log formatter includes extra fields

```bash
uv run python scripts/smoke_test_stderr_formatter.py
```

## Utility

**`cleanup-manual-jobs.sh`** - Clean up old manual scraper jobs

```bash
./scripts/cleanup-manual-jobs.sh --dry-run          # Preview what would be deleted
./scripts/cleanup-manual-jobs.sh --age 24           # Delete jobs older than 24 hours
```

**`check_coverage.sh`** - Check code coverage

```bash
./scripts/check_coverage.sh
```

**`view-audit.sh`** - View audit logs

```bash
./scripts/view-audit.sh
```

**`setup-mac-wake.sh`** - Set up Mac wake automation for scheduled scrapes

```bash
./scripts/setup-mac-wake.sh
```

## Quick Reference

| Task | Command |
|------|---------|
| Deploy to K3s | `./scripts/deploy-k3s.sh` |
| Test K3s deployment | `./scripts/test-k3s.sh` |
| Manual scrape | `./scripts/trigger-scrape.sh` |
| Clean up old jobs | `./scripts/cleanup-manual-jobs.sh --age 24` |
| Smoke test stderr fmt | `uv run python scripts/smoke_test_stderr_formatter.py` |

---

See individual scripts for detailed usage and options.
