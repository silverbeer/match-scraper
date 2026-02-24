# 🚀 K3s Deployment - Pick Up on Mini

**Status:** Ready to deploy on Mac Mini with Rancher Desktop
**Branch:** `feature/k3s-local-deployment`
**Date:** 2025-10-18

## What We Built

Complete local K3s deployment solution for match-scraper with RabbitMQ to populate prod Supabase (missingtable.com).

### New Files Created

**RabbitMQ Deployment (`k3s/rabbitmq/`):**
- `namespace.yaml` - Shared namespace for all components
- `secret.yaml` - RabbitMQ credentials (admin/admin123)
- `configmap.yaml` - RabbitMQ configuration
- `statefulset.yaml` - RabbitMQ with 5Gi persistent storage
- `service.yaml` - Internal service + management UI (NodePort 30672)

**Match-Scraper Deployment (`k3s/match-scraper/`):**
- `configmap.yaml` - Scraper config with RabbitMQ connection
- `secret.yaml` - API tokens (optional when using queue)
- `cronjob.yaml` - Daily 6 AM UTC schedule

**Scripts:**
- `scripts/deploy-k3s.sh` - One-command deployment
- `scripts/test-k3s.sh` - Testing and monitoring tools

**Documentation:**
- `docs/deployment/k3s-deployment.md` - Complete deployment guide
- Updated `README.md` and `docs/README.md` with k3s info

## Architecture

```
match-scraper CronJob (k3s)
    ↓
RabbitMQ (k3s) - queue: "matches"
    ↓
missing-table Celery workers (k3s)
    ↓
Supabase (dev or prod)
```

## Prerequisites on Mini

✅ Rancher Desktop installed and running
✅ Kubernetes enabled in Rancher Desktop
✅ kubectl configured to use `rancher-desktop` context
✅ Docker running (bundled with Rancher Desktop)

## Deployment Steps on Mini

### 1. Get the Code

```bash
cd ~/gitrepos/match-scraper  # or wherever you keep it
git fetch origin
git checkout feature/k3s-local-deployment
git pull origin feature/k3s-local-deployment
```

### 2. Verify Rancher Desktop

```bash
# Check Rancher Desktop is running with Kubernetes
kubectl config get-contexts

# You should see rancher-desktop in the list
# Switch to it if not current
kubectl config use-context rancher-desktop

# Verify connection
kubectl get nodes
```

### 3. Deploy Everything

```bash
# One command deploys RabbitMQ + match-scraper
./scripts/deploy-k3s.sh
```

This will:
- ✅ Build Docker image locally
- ✅ Import image into Rancher Desktop's containerd
- ✅ Deploy RabbitMQ with persistent storage
- ✅ Deploy match-scraper CronJob
- ✅ Verify everything is running

### 4. Test the Pipeline

```bash
# Trigger a manual test job
./scripts/test-k3s.sh trigger

# Watch the logs in real-time
./scripts/test-k3s.sh logs

# Check RabbitMQ status
./scripts/test-k3s.sh rabbitmq
```

### 5. Access RabbitMQ Management UI

Open in browser: http://localhost:30672

**Credentials:**
- Username: `admin`
- Password: `admin123`

Check the `matches` queue to see messages being queued.

## Configuration

### Current Settings

**Scraper (`k3s/match-scraper/configmap.yaml`):**
- Age Group: U14
- Division: Northeast
- Schedule: Daily 6 AM UTC
- Date Range: Yesterday to tomorrow (default)
- RabbitMQ: `amqp://admin:admin123@rabbitmq.match-scraper:5672//`

**Queue Behavior:**
- Uses `--use-queue` by default (sends to RabbitMQ)
- Matches are queued to the `matches` queue
- No direct API calls from scraper

### Supabase Target

The match-scraper just queues messages. Celery workers consume from the queue and write to Supabase.

**Environments**: Prod and local only. There is no dev environment.

- **Prod workers** consume from `matches.prod` → write to prod Supabase (missingtable.com)
- **Local workers** consume from `matches.local` → write to local Supabase (localhost:54321)

See [workers/README.md](../../k3s/workers/README.md) for worker deployment details.

## Monitoring

### Check Status

```bash
# Overall status
./scripts/test-k3s.sh status

# CronJob details
kubectl get cronjob -n match-scraper

# Recent jobs
kubectl get jobs -n match-scraper --sort-by=.metadata.creationTimestamp

# RabbitMQ pods
kubectl get pods -n match-scraper -l app=rabbitmq
```

### View Logs

```bash
# Latest job logs
./scripts/test-k3s.sh logs

# Specific pod logs
kubectl logs -n match-scraper <pod-name> --tail=100 -f

# RabbitMQ logs
kubectl logs -n match-scraper rabbitmq-0
```

### Check RabbitMQ Queues

```bash
# From CLI
kubectl exec -n match-scraper rabbitmq-0 -- rabbitmqctl list_queues name messages consumers

# Or use management UI at http://localhost:30672
```

## Troubleshooting

### Image Not Found

If you see `ErrImageNeverPull` or `ImagePullBackOff`:

```bash
# Rebuild and import image
docker build -t match-scraper:latest .
docker save match-scraper:latest -o /tmp/match-scraper.tar

# Import to Rancher Desktop (varies by Rancher version)
# Try one of these:
nerdctl -n k8s.io load -i /tmp/match-scraper.tar
# OR
ctr -n k8s.io images import /tmp/match-scraper.tar
```

### RabbitMQ Not Starting

```bash
# Check pod status
kubectl describe pod rabbitmq-0 -n match-scraper

# Check logs
kubectl logs rabbitmq-0 -n match-scraper

# Check persistent volume
kubectl get pvc -n match-scraper
```

### No Messages in Queue

**Check:**
1. Job completed successfully: `kubectl get jobs -n match-scraper`
2. Job logs show RabbitMQ connection: `./scripts/test-k3s.sh logs`
3. RabbitMQ is reachable from pod

### Workers Not Processing

**This is a missing-table issue, not match-scraper:**

1. Verify workers are deployed and running
2. Check worker logs for errors
3. Confirm workers are connected to RabbitMQ
4. Verify Supabase credentials are correct

## Next Steps After Deployment

1. ✅ Deploy everything: `./scripts/deploy-k3s.sh`
2. ✅ Trigger test job: `./scripts/test-k3s.sh trigger`
3. ✅ Verify messages in RabbitMQ: http://localhost:30672
4. ✅ Ensure missing-table workers are running and connected
5. ✅ Check data appears in prod Supabase
6. 🎯 Once validated, switch workers to prod Supabase

## Important Notes

- **Docker image is built locally** - No need for GCR or registry
- **imagePullPolicy: Never** - Uses local image only
- **Persistent storage** - RabbitMQ data survives pod restarts
- **NodePort 30672** - RabbitMQ UI accessible on Mini at localhost:30672
- **Default schedule** - Daily 6 AM UTC (same as production)

## Documentation

Full documentation available at:
- **[K3s Deployment Guide](docs/deployment/k3s-deployment.md)** - Complete guide
- **[README.md](README.md#k3srancher-local-deployment)** - Quick start

## Questions/Issues

If you run into issues:
1. Check logs: `./scripts/test-k3s.sh logs`
2. Check RabbitMQ: `./scripts/test-k3s.sh rabbitmq`
3. Review documentation: `docs/deployment/k3s-deployment.md`
4. Check pod status: `kubectl get pods -n match-scraper`

---

**Ready to deploy!** 🚀

Start with: `./scripts/deploy-k3s.sh`
