# RabbitMQ Fanout Pattern: Dev/Prod Environment Separation

**Last Updated**: 2025-10-21

## Overview

This document describes the RabbitMQ fanout exchange pattern used to route match data to both development and production environments from a single scrape operation.

## Motivation

### The Problem
- **Don't want to hammer mlssoccer.com**: Scraping the same data twice (once for dev, once for prod) puts unnecessary load on the source website
- **Want prod as primary**: Production should be the default target for daily automated scrapes
- **Need dev data**: Development environment needs real data for testing, preferably identical to prod
- **Manual targeting**: Sometimes need to send data only to dev or only to prod

### The Solution
Use RabbitMQ's fanout exchange pattern to publish once and route to multiple queues automatically.

## Architecture

```
┌──────────────────┐
│  Match Scraper   │
│  (Daily Cron)    │
└────────┬─────────┘
         │
         │ Publish
         ▼
┌────────────────────┐
│ matches-fanout     │  ◄── Fanout Exchange
│ (Exchange)         │
└────────┬───────────┘
         │
         ├─────────────────────┬──────────────────────┐
         │                     │                      │
         ▼                     ▼                      ▼
  ┌─────────────┐      ┌─────────────┐      (Future: staging)
  │matches.prod │      │matches.dev  │
  │  (Queue)    │      │  (Queue)    │
  └──────┬──────┘      └──────┬──────┘
         │                     │
         │                     │
         ▼                     ▼
  ┌─────────────┐      ┌─────────────┐
  │Prod Workers │      │Dev Workers  │
  │  (2 pods)   │      │  (2 pods)   │
  └──────┬──────┘      └──────┬──────┘
         │                     │
         ▼                     ▼
  ┌─────────────┐      ┌─────────────┐
  │Prod Supabase│      │Dev Supabase │
  │             │      │             │
  └─────────────┘      └─────────────┘
```

## Components

### 1. Fanout Exchange: `matches-fanout`

**Type**: Fanout
**Purpose**: Routes incoming messages to all bound queues
**Configuration**: Durable, non-auto-delete

```yaml
# Defined in: k3s/rabbitmq/configmap.yaml
exchanges:
  - name: matches-fanout
    type: fanout
    durable: true
```

**How it works**:
- Receives messages from scraper
- Automatically copies message to ALL bound queues
- No routing key needed (fanout ignores routing keys)
- Messages appear in both `matches.prod` and `matches.dev`

### 2. Production Queue: `matches.prod`

**Purpose**: Holds matches destined for production Supabase
**Consumers**: Prod workers (2 replicas)
**Configuration**: Durable, classic queue

Binding:
```yaml
bindings:
  - source: matches-fanout
    destination: matches.prod
    destination_type: queue
```

### 3. Development Queue: `matches.dev`

**Purpose**: Holds matches destined for development Supabase
**Consumers**: Dev workers (2 replicas)
**Configuration**: Durable, classic queue

Binding:
```yaml
bindings:
  - source: matches-fanout
    destination: matches.dev
    destination_type: queue
```

### 4. Worker Pools

#### Production Workers
- **Deployment**: `missing-table-celery-worker-prod`
- **Replicas**: 2
- **Queue**: `matches.prod`
- **Target**: Production Supabase
- **Environment**: `production`

```bash
# Check prod workers
kubectl get pods -n match-scraper -l environment=prod
```

#### Development Workers
- **Deployment**: `missing-table-celery-worker-dev`
- **Replicas**: 2
- **Queue**: `matches.dev`
- **Target**: Development Supabase
- **Environment**: `development`

```bash
# Check dev workers
kubectl get pods -n match-scraper -l environment=dev
```

## Usage Patterns

### 1. Default: Fanout to Both (Automated Daily Scrape)

The cronjob runs with no special flags, defaulting to fanout exchange:

```yaml
# k3s/match-scraper/cronjob.yaml
command: ["python", "-m", "src.cli.main", "scrape"]
# Defaults to --exchange matches-fanout
```

**Result**: Match data flows to BOTH prod and dev

### 2. Target Prod Only (Manual)

Publish directly to prod queue, bypassing fanout:

```bash
# Trigger manual job targeting prod only
kubectl create job --from=cronjob/match-scraper-cronjob prod-test-$(date +%s) -n match-scraper

# Or run locally
python -m src.cli.main scrape --queue matches.prod
```

**Result**: Match data goes ONLY to prod

### 3. Target Dev Only (Manual)

Publish directly to dev queue:

```bash
# Run locally targeting dev
python -m src.cli.main scrape --queue matches.dev

# Or create k8s job (would need custom job manifest)
```

**Result**: Match data goes ONLY to dev

### 4. Disable Queue Submission

For local testing without sending to any queue:

```bash
python -m src.cli.main scrape --no-submit-queue
```

## CLI Options

### New Routing Options

```bash
# Fanout to both (default)
python -m src.cli.main scrape

# Explicit fanout exchange
python -m src.cli.main scrape --exchange matches-fanout

# Target specific queue
python -m src.cli.main scrape --queue matches.dev
python -m src.cli.main scrape --queue matches.prod

# Disable queue submission
python -m src.cli.main scrape --no-submit-queue
```

### Priority
1. If `--queue` is specified → Direct queue routing
2. If `--exchange` is specified → Exchange routing
3. If neither → Defaults to `--exchange matches-fanout`

## Monitoring

### Check Exchange and Bindings

```bash
# List exchanges
kubectl exec -n match-scraper rabbitmq-0 -- rabbitmqctl list_exchanges

# List queue bindings
kubectl exec -n match-scraper rabbitmq-0 -- rabbitmqctl list_bindings
```

### Check Queue Status

```bash
# View all queues with message counts
kubectl exec -n match-scraper rabbitmq-0 -- \
  rabbitmqctl list_queues name messages consumers

# Expected output:
# matches.prod     0    2  ← 2 prod workers consuming
# matches.dev      0    2  ← 2 dev workers consuming
```

### Check Worker Logs

```bash
# Prod worker logs
kubectl logs -n match-scraper -l environment=prod -f

# Dev worker logs
kubectl logs -n match-scraper -l environment=dev -f
```

### RabbitMQ Management UI

Access at: http://localhost:30672

- Username: `admin`
- Password: `admin123`

Navigate to:
- **Exchanges** → `matches-fanout` to see bindings
- **Queues** → `matches.prod` or `matches.dev` to see consumers and messages

## Deployment

### Initial Setup

```bash
# 1. Deploy RabbitMQ with fanout exchange
./scripts/deploy-k3s.sh

# 2. Deploy workers (dev + prod)
./scripts/deploy-k3s.sh --deploy-workers

# Note: Prod workers require prod secrets to be configured first
# See: k3s/workers/README.md
```

### Verify Deployment

```bash
# 1. Check RabbitMQ definitions loaded
kubectl logs -n match-scraper rabbitmq-0 | grep "definitions"

# 2. Check exchange and queues exist
kubectl exec -n match-scraper rabbitmq-0 -- \
  rabbitmqctl list_exchanges | grep matches-fanout

kubectl exec -n match-scraper rabbitmq-0 -- \
  rabbitmqctl list_queues | grep matches

# 3. Check workers are running
kubectl get deployments -n match-scraper -l app=missing-table-worker

# 4. Trigger test scrape
kubectl create job --from=cronjob/match-scraper-cronjob test-$(date +%s) -n match-scraper

# 5. Watch queues (should see messages appear in both, then get consumed)
watch -n 1 'kubectl exec -n match-scraper rabbitmq-0 -- rabbitmqctl list_queues'
```

## Benefits

1. **Single Scrape Operation**: mlssoccer.com is only hit once, regardless of how many environments need data

2. **Identical Data**: Dev and prod get exactly the same data from the same scrape run

3. **Independent Scaling**: Can scale dev and prod workers independently
   ```bash
   kubectl scale deployment missing-table-celery-worker-prod -n match-scraper --replicas=4
   kubectl scale deployment missing-table-celery-worker-dev -n match-scraper --replicas=1
   ```

4. **Easy to Pause Dev**: Can pause dev workers without affecting prod
   ```bash
   kubectl scale deployment missing-table-celery-worker-dev -n match-scraper --replicas=0
   ```

5. **Flexible Targeting**: Manual runs can target specific environments when needed

6. **Easy to Extend**: Adding staging environment is just another queue + binding

## Trade-offs

### Advantages
- ✅ Minimal load on source website
- ✅ Guaranteed identical data across environments
- ✅ Clean separation of concerns
- ✅ Independent worker lifecycle management
- ✅ Flexible manual overrides

### Considerations
- ⚠️ Requires RabbitMQ exchange configuration
- ⚠️ Both environments get ALL data (can't filter by environment at publish time)
- ⚠️ More complex than direct queue publishing (but more powerful)

## Future Enhancements

### Staging Environment

Add a third queue for staging:

```yaml
# Add to k3s/rabbitmq/configmap.yaml definitions
queues:
  - name: matches.staging
    durable: true

bindings:
  - source: matches-fanout
    destination: matches.staging
    destination_type: queue
```

Deploy staging workers:
```bash
kubectl apply -f k3s/workers/staging-configmap.yaml
kubectl apply -f k3s/workers/staging-deployment.yaml
```

### Selective Routing

Use a **topic exchange** instead of fanout for more control:

```yaml
exchanges:
  - name: matches-topic
    type: topic

bindings:
  - source: matches-topic
    destination: matches.prod
    routing_key: "matches.prod.*"
  - source: matches-topic
    destination: matches.dev
    routing_key: "matches.dev.*"
  - source: matches-topic
    destination: matches.all
    routing_key: "matches.*"  # Catches all
```

Publish with routing key:
```python
# In queue_client.py
result = self.app.send_task(
    ...,
    exchange="matches-topic",
    routing_key="matches.prod.daily"
)
```

## Troubleshooting

### Messages not appearing in queues

```bash
# 1. Check exchange exists and has bindings
kubectl exec -n match-scraper rabbitmq-0 -- rabbitmqctl list_bindings

# 2. Check scraper is publishing to exchange (not queue)
kubectl logs -n match-scraper -l app=match-scraper --tail=50 | grep "exchange"

# Expected: "Match submitted to exchange 'matches-fanout'"
# Not: "Match submitted to queue 'matches'"
```

### Workers not consuming

```bash
# Check worker queue configuration
kubectl get deployment missing-table-celery-worker-dev -n match-scraper -o yaml | grep -A 3 args

# Should show: --queues=matches.dev (not --queues=matches)
```

### Only one environment receiving data

```bash
# Check both queues are bound to exchange
kubectl exec -n match-scraper rabbitmq-0 -- \
  rabbitmqctl list_bindings | grep matches-fanout
```

## References

- **RabbitMQ Configuration**: `k3s/rabbitmq/configmap.yaml`
- **Worker Manifests**: `k3s/workers/`
- **Deployment Script**: `scripts/deploy-k3s.sh`
- **Worker Setup Guide**: `k3s/workers/README.md`
- **Queue Client**: `src/celery/queue_client.py`

## Related Documentation

- [Async Message Queue Architecture](async-message-queue-architecture.md) - Complete pipeline overview
- [K3s Deployment Guide](../deployment/k3s-deployment.md) - Local deployment setup
- [CLI Usage Guide](../guides/cli-usage.md) - CLI options and examples
