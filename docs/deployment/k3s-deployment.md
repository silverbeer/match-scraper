# K3s Deployment Guide

This guide covers deploying the match-scraper pipeline to the M4 Mac rancher-desktop K3s cluster.

## Overview

**Architecture:**
```
match-scraper-agent (CronJob) → RabbitMQ → Celery workers → prod Supabase
       ↓                            ↓              ↓
   rancher-desktop K3s       rancher-desktop   rancher-desktop
   (M4 Mac)                  K3s (M4 Mac)     K3s (M4 Mac)
```

All scraper pipeline components run locally on the M4 Mac. This IS the production scraper — it writes to **prod Supabase** (missingtable.com).

**Environments:** Prod and local only. There is no dev environment.

**Benefits:**
- No cloud costs for the scraper pipeline
- Full local control
- Queue-based architecture for reliability

## Prerequisites

1. **Rancher Desktop** installed and running on M4 Mac
2. **kubectl** configured with `rancher-desktop` context
3. **Docker** for building images

## Quick Start

### 1. Deploy Everything

```bash
# One-command deployment (RabbitMQ + match-scraper)
./scripts/deploy-k3s.sh
```

This script will:
1. Build the Docker image
2. Import it into K3s
3. Deploy RabbitMQ
4. Deploy match-scraper CronJob
5. Verify everything is running

### 2. Test the Pipeline

```bash
# Trigger a manual job
./scripts/test-k3s.sh trigger

# View logs
./scripts/test-k3s.sh logs

# Check RabbitMQ queues
./scripts/test-k3s.sh rabbitmq
```

### 3. Verify End-to-End

1. Check RabbitMQ management UI: http://localhost:30672
   - Username: `admin`
   - Password: `admin123`
2. Confirm messages are queued in the `matches.prod` queue
3. Ensure Celery workers process the messages
4. Verify data appears in prod Supabase

## Configuration

### Match-Scraper Configuration

Edit `k3s/match-scraper/configmap.yaml`:

```yaml
data:
  # What to scrape
  AGE_GROUP: "U14"
  DIVISION: "Northeast"

  # Where to send data (RabbitMQ)
  RABBITMQ_URL: "amqp://admin:admin123@rabbitmq.match-scraper:5672//"

  # Logging
  LOG_LEVEL: "INFO"

  # Browser settings
  HEADLESS: "true"
  BROWSER_TIMEOUT: "30000"
```

Apply changes:
```bash
kubectl apply -f k3s/match-scraper/configmap.yaml
```

### CronJob Schedule

Edit `k3s/match-scraper/cronjob.yaml`:

```yaml
spec:
  schedule: "0 14 * * *"  # Daily at 14:00 UTC
  timeZone: "UTC"
```

Apply changes:
```bash
kubectl apply -f k3s/match-scraper/cronjob.yaml
```

### Completeness backfill CronJob (SB-1786)

`k3s/completeness/cronjob.yaml` runs `match-scraper-agent backfill --env prod
--submit` daily at 22:40 America/New_York. It sends completed official League
and Flex results that have no MT row, confirms they landed, and alerts
Telegram. It reads its queue and MT API from `match-scraper-agent-config`
(`AGENT_QUEUE_NAME`, `AGENT_MISSING_TABLE_API_URL`) and refuses to publish if
that pair is not prod/prod or non-prod/non-prod.

It mounts the `agent-state` PVC at `/data/agent-state` and writes
`completeness.json` there (`AGENT_COMPLETENESS_STATE_PATH`). The **digest**
CronJob (`k3s/digest/cronjob.yaml`) now mounts the same PVC **read-only** to
read that file for its "N official results not in MT" line. Without the mount
the digest still runs; it just leaves that line out.

Nothing applies `k3s/` on merge. Apply both by hand:

```bash
kubectl apply -f k3s/completeness/cronjob.yaml
kubectl apply -f k3s/digest/cronjob.yaml
```

Dry-run it first from a shell with the prod settings:
`uv run match-scraper-agent backfill --env prod` (publishes nothing, alerts
nothing). Exit 10 means "ran, with findings" and the manifest treats it as
success; exit 1 (feed or MT unreadable, publish guard, more than
`--max-changes` results) fails the Job, and the Job is not retried.

### Reconcile CronJob (SB-1787)

`k3s/reconcile/cronjob.yaml` runs `match-scraper-agent reconcile --env prod
--submit` every Monday at 05:00 America/New_York. It compares past MT League
and Flex matches (Homegrown, Flex, and the Academy conferences in
`AGENT_ACADEMY_CONFERENCES`) with the official feed and sends the feed's
fixture for each score, home/away, status or date that differs. Like the
completeness job it takes its queue and MT API from
`match-scraper-agent-config` and refuses to publish if that pair disagrees.

It needs the MT API key to be an admin or a service account with
`manage_matches`: `/api/agent/season-matches` refuses anything less.

It mounts the `agent-state` PVC at `/data/agent-state` and writes one change
log per submitting run to `/data/agent-state/reconcile/<run>.json`
(`AGENT_RECONCILE_LOG_DIR`).

```bash
kubectl apply -f k3s/reconcile/cronjob.yaml
```

Dry-run it first: `uv run match-scraper-agent reconcile --env prod`. Exit 10
is "ran, with findings" and counts as success; exit 1 (feed or MT unreadable,
publish guard, more than `--max-changes` (100) corrections) fails the Job,
which is not retried.

### RabbitMQ Configuration

Edit `k3s/rabbitmq/secret.yaml` to change credentials:

```bash
# Generate new credentials
echo -n "new-username" | base64
echo -n "new-password" | base64

# Update secret.yaml with new values
kubectl apply -f k3s/rabbitmq/secret.yaml

# Restart RabbitMQ
kubectl rollout restart statefulset rabbitmq -n match-scraper
```

## Queue Architecture

The scraper publishes to the `matches-fanout` exchange. Messages are routed to bound queues:

| Queue | Workers | Supabase | Purpose |
|-------|---------|----------|---------|
| `matches.prod` | Prod Celery workers | `ppgxasqgqbnauvxozmjw.supabase.co` | Production (missingtable.com) |
| `matches.local` | Local Celery workers | `localhost:54321` | Local development |

See [workers/README.md](../../k3s/workers/README.md) for worker deployment details.

## Monitoring and Troubleshooting

### Check Status

```bash
# Overall status
./scripts/test-k3s.sh status

# RabbitMQ status
./scripts/test-k3s.sh rabbitmq

# View logs
./scripts/test-k3s.sh logs
```

### Manual Job Trigger

```bash
# Trigger a test job
./scripts/test-k3s.sh trigger

# Monitor logs in real-time
kubectl logs -n match-scraper -l app=match-scraper --tail=100 -f
```

### RabbitMQ Management UI

Access at: http://localhost:30672

**Check queues:**
- Navigate to "Queues" tab
- Look for `matches.prod` and `matches.local` queues
- Check message count and consumer status

### Common Issues

#### 1. Image Not Found

**Error:** `ImagePullBackOff` or `ErrImageNeverPull`

**Solution:**
```bash
# Rebuild and import image
./scripts/deploy-k3s.sh
```

#### 2. RabbitMQ Not Ready

**Error:** Pod stuck in `Pending` or `CrashLoopBackOff`

**Solution:**
```bash
# Check pod logs
kubectl logs -n match-scraper -l app=rabbitmq

# Check storage
kubectl get pvc -n match-scraper

# If storage issues, delete and recreate
kubectl delete statefulset rabbitmq -n match-scraper
./scripts/deploy-k3s.sh --rabbitmq-only
```

#### 3. No Messages in Queue

**Check:**
1. CronJob ran: `kubectl get jobs -n match-scraper`
2. Job succeeded: `./scripts/test-k3s.sh logs`
3. RabbitMQ connection in logs: Look for "Celery client initialized"

#### 4. Workers Not Processing Messages

```bash
# Check worker status
kubectl get pods -n match-scraper -l app=missing-table-worker

# Check worker logs
kubectl logs -n match-scraper -l environment=prod --tail=100
```

## Maintenance

### Update Docker Image

```bash
# Rebuild and redeploy
./scripts/deploy-k3s.sh

# Or rebuild only
docker build -t match-scraper:latest .
docker save match-scraper:latest -o /tmp/match-scraper.tar
sudo k3s ctr images import /tmp/match-scraper.tar
```

### Clean Up Test Jobs

```bash
# Delete all test jobs
./scripts/test-k3s.sh cleanup
```

## Resource Usage

**RabbitMQ:**
- CPU: 100m request, 500m limit
- Memory: 256Mi request, 512Mi limit
- Storage: 5Gi persistent volume

**Match-Scraper (per job):**
- CPU: 500m request, 1000m limit
- Memory: 1Gi request, 2Gi limit
- Runs for ~2-5 minutes per job

**Total K3s footprint:** ~3-4Gi RAM, 5Gi storage
