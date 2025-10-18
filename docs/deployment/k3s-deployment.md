# K3s Local Deployment Guide

This guide covers deploying match-scraper and RabbitMQ to your local k3s/Rancher cluster for cost-effective production data collection.

## Overview

**Architecture:**
```
match-scraper (CronJob) → RabbitMQ → missing-table workers → Supabase (prod/dev)
       ↓                      ↓                ↓
   k3s cluster         k3s cluster       k3s cluster
```

**Benefits:**
- ✅ No GKE/cloud costs
- ✅ Same queue-based architecture as production
- ✅ Full local control
- ✅ Easy dev/prod environment switching (via missing-table workers)

## Prerequisites

1. **K3s or Rancher Desktop** installed and running
2. **kubectl** configured to connect to your k3s cluster
3. **Docker** for building images
4. **missing-table backend** with Celery workers ready to deploy

## Quick Start

### 1. Deploy Everything

```bash
# One-command deployment (RabbitMQ + match-scraper)
./scripts/deploy-k3s.sh
```

This script will:
1. Build the Docker image
2. Import it into k3s
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
2. Confirm messages are queued in the `matches` queue
3. Ensure missing-table workers process the messages
4. Verify data appears in Supabase

## Detailed Deployment

### Step-by-Step Deployment

#### 1. Deploy RabbitMQ Only

```bash
./scripts/deploy-k3s.sh --rabbitmq-only
```

This creates:
- RabbitMQ StatefulSet with persistent storage
- Internal service at `rabbitmq.match-scraper:5672`
- Management UI at `http://localhost:30672`

#### 2. Deploy Match-Scraper Only

```bash
./scripts/deploy-k3s.sh --scraper-only
```

This creates:
- CronJob scheduled for daily 6 AM UTC
- ConfigMap with scraping configuration
- Uses local Docker image (no registry pull)

#### 3. Skip Docker Build (Use Existing Image)

```bash
./scripts/deploy-k3s.sh --skip-build
```

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
  schedule: "0 6 * * *"  # Daily at 6 AM UTC
  timeZone: "UTC"
```

Apply changes:
```bash
kubectl apply -f k3s/match-scraper/cronjob.yaml
```

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

## Environment Switching (Dev/Prod)

The match-scraper always queues messages to RabbitMQ. Environment switching happens in the **missing-table Celery workers**.

### For Missing-Table Workers

Configure workers to point to different Supabase instances:

**Production:**
```yaml
# missing-table ConfigMap
SUPABASE_URL: "https://your-prod-project.supabase.co"
SUPABASE_KEY: "your-prod-key"
```

**Development:**
```yaml
# missing-table ConfigMap
SUPABASE_URL: "https://your-dev-project.supabase.co"
SUPABASE_KEY: "your-dev-key"
```

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
- Look for `matches` queue
- Check message count and consumer status

**View messages:**
- Click on `matches` queue
- Use "Get messages" to peek at queued data

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

**Debug:**
```bash
# Trigger manual job with verbose logging
kubectl create job --from=cronjob/match-scraper-cronjob debug-$(date +%s) -n match-scraper

# Check logs
./scripts/test-k3s.sh logs
```

#### 4. Workers Not Processing Messages

**This is a missing-table issue, not match-scraper.**

**Check:**
1. Workers are running
2. Workers are connected to same RabbitMQ (`rabbitmq.match-scraper:5672`)
3. Workers are consuming from `matches` queue

## Maintenance

### Update Configuration

```bash
# Edit ConfigMap
kubectl edit configmap match-scraper-config -n match-scraper

# Changes apply to next job run (no restart needed for CronJob)
```

### Update Docker Image

```bash
# Rebuild and redeploy
./scripts/deploy-k3s.sh

# Or rebuild only
docker build -f Dockerfile.gke -t match-scraper:latest .
docker save match-scraper:latest -o /tmp/match-scraper.tar
sudo k3s ctr images import /tmp/match-scraper.tar
```

### Clean Up Test Jobs

```bash
# Delete all test jobs
./scripts/test-k3s.sh cleanup
```

### View Job History

```bash
# See recent jobs
kubectl get jobs -n match-scraper --sort-by=.metadata.creationTimestamp

# Check specific job
kubectl describe job <job-name> -n match-scraper
```

## Backup and Recovery

### Backup RabbitMQ Data

```bash
# Get persistent volume
kubectl get pvc -n match-scraper

# Backup data (adjust path as needed)
kubectl exec -n match-scraper rabbitmq-0 -- tar czf - /var/lib/rabbitmq/mnesia > rabbitmq-backup.tar.gz
```

### Restore RabbitMQ Data

```bash
# Copy backup to pod
kubectl cp rabbitmq-backup.tar.gz match-scraper/rabbitmq-0:/tmp/

# Restore (adjust paths)
kubectl exec -n match-scraper rabbitmq-0 -- tar xzf /tmp/rabbitmq-backup.tar.gz -C /
```

## Uninstall

### Remove Everything

```bash
# Delete match-scraper
kubectl delete -f k3s/match-scraper/cronjob.yaml
kubectl delete -f k3s/match-scraper/configmap.yaml
kubectl delete -f k3s/match-scraper/secret.yaml

# Delete RabbitMQ (WARNING: This deletes data)
kubectl delete -f k3s/rabbitmq/statefulset.yaml
kubectl delete -f k3s/rabbitmq/service.yaml
kubectl delete -f k3s/rabbitmq/configmap.yaml
kubectl delete -f k3s/rabbitmq/secret.yaml

# Delete namespace
kubectl delete namespace match-scraper
```

### Remove Docker Image

```bash
# From k3s
sudo k3s ctr images rm docker.io/library/match-scraper:latest

# From Docker
docker rmi match-scraper:latest
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

**Total k3s footprint:** ~3-4Gi RAM, 5Gi storage

## Production Considerations

### Security

1. **Change RabbitMQ credentials** in `k3s/rabbitmq/secret.yaml`
2. **Restrict NodePort** access to RabbitMQ management UI
3. **Enable TLS** for RabbitMQ connections (optional)

### Monitoring

Consider adding:
- Prometheus metrics from RabbitMQ (port 15692)
- Alerting for failed jobs
- Queue depth monitoring

### Scaling

For higher frequency scraping:
1. Adjust CronJob schedule (e.g., every 6 hours)
2. Increase RabbitMQ resources if queue builds up
3. Scale missing-table workers to process faster

## Next Steps

1. ✅ Deploy RabbitMQ and match-scraper
2. ✅ Trigger test job and verify pipeline
3. ✅ Configure missing-table workers to consume from queue
4. ✅ Validate data in Supabase
5. 📋 Set up monitoring/alerts (optional)
6. 📋 Schedule regular backups (optional)
