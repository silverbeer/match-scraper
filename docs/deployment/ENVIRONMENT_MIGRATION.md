# Environment Migration: Prod → Dev Only

**Date:** 2025-11-14
**Status:** Completed

## Summary

As of November 14, 2025, the Missing Table application operates with a single GCP environment:
- **Production URL** (missingtable.com) now points to the **dev environment**
- Match-scraper now fanouts to **local** and **dev** only
- The **prod** environment has been deprecated and removed

## Changes Made

### 1. RabbitMQ Configuration

**Old Setup:**
```
matches-fanout exchange
  ├─→ matches.prod queue → prod workers
  └─→ matches.dev queue  → dev workers
```

**New Setup:**
```
matches-fanout exchange
  ├─→ matches.local queue → local workers (local development)
  └─→ matches.dev queue   → dev workers (production)
```

### 2. Queue Configuration

#### Removed
- `matches.prod` queue
- Binding: `matches-fanout` → `matches.prod`
- `prod-deployment.yaml` (deprecated)
- `prod-configmap.yaml` (deprecated)

#### Added
- `matches.local` queue
- Binding: `matches-fanout` → `matches.local`
- `local-deployment.yaml` (new)
- `local-configmap.yaml` (new)

### 3. Worker Deployments

| Environment | Queue | Supabase | Status |
|-------------|-------|----------|--------|
| **local** | `matches.local` | `http://localhost:54321` | ✅ New |
| **dev** | `matches.dev` | `ppgxasqgqbnauvxozmjw.supabase.co` | ✅ Active (serves missingtable.com) |
| **prod** | `matches.prod` | `iueycteoamjbygwhnovz.supabase.co` | ❌ Deprecated |

## Migration Steps

### For Existing K3s/K8s Clusters

#### Step 1: Update RabbitMQ Configuration

```bash
# Apply updated RabbitMQ config with new queue definitions
kubectl apply -f k3s/rabbitmq/configmap.yaml

# Restart RabbitMQ to load new definitions
kubectl delete pod rabbitmq-0 -n match-scraper
# StatefulSet will recreate it with new config
```

#### Step 2: Deploy Local Workers (Optional)

```bash
# Deploy local worker configmap and deployment
kubectl apply -f k3s/workers/local-configmap.yaml
kubectl apply -f k3s/workers/local-deployment.yaml

# Verify local workers are running
kubectl get pods -n match-scraper -l environment=local
```

#### Step 3: Remove Prod Workers

```bash
# Scale down prod workers to zero (graceful shutdown)
kubectl scale deployment missing-table-celery-worker-prod -n match-scraper --replicas=0

# Wait for all prod workers to finish processing
kubectl get pods -n match-scraper -l environment=prod

# Delete prod deployment
kubectl delete deployment missing-table-celery-worker-prod -n match-scraper

# Delete prod configmap
kubectl delete configmap missing-table-worker-prod-config -n match-scraper

# Delete prod secrets (if they exist separately)
kubectl delete secret missing-table-worker-prod-secrets -n match-scraper --ignore-not-found
```

#### Step 4: Verify New Setup

```bash
# Check RabbitMQ queues
kubectl exec -n match-scraper rabbitmq-0 -- \
  rabbitmqctl list_queues name messages consumers

# Expected output:
# matches.local    0    1    # 1 local worker
# matches.dev      0    2    # 2 dev workers
# (matches.prod should be gone)

# Check bindings
kubectl exec -n match-scraper rabbitmq-0 -- \
  rabbitmqctl list_bindings

# Expected:
# matches-fanout → matches.local
# matches-fanout → matches.dev
```

## Impact on Match-Scraper

### No Code Changes Required

The match-scraper code **does not need changes** because it uses the fanout exchange pattern:

```python
# src/celery/queue_client.py (unchanged)
client = MatchQueueClient()  # Uses matches-fanout by default
client.submit_match(match_data)  # Automatically routes to ALL bound queues
```

### Automatic Fanout Behavior

When match-scraper publishes to `matches-fanout`:
1. Message is duplicated
2. One copy goes to `matches.local` → local workers
3. One copy goes to `matches.dev` → dev workers
4. No copy goes to prod (queue removed)

### Daily CronJob

The daily match-scraper CronJob continues to work without modification:
- Runs at 6 AM UTC
- Publishes to `matches-fanout` exchange
- Messages automatically route to local + dev
- Both environments receive all matches

## Verification

### 1. Trigger a Test Run

```bash
# Manually trigger scraper
./scripts/test-k3s.sh trigger

# Watch logs
./scripts/test-k3s.sh logs
```

### 2. Check Queue Activity

```bash
# Monitor queue depths
watch -n 2 'kubectl exec -n match-scraper rabbitmq-0 -- \
  rabbitmqctl list_queues name messages consumers'

# Should see:
# matches.local    N    1    # Messages being processed
# matches.dev      N    2    # Messages being processed
```

### 3. Verify RabbitMQ UI

Open http://localhost:30672
- **Username:** admin
- **Password:** admin123

**Queues Tab:**
- ✅ `matches.local` exists with 1 consumer
- ✅ `matches.dev` exists with 2 consumers
- ❌ `matches.prod` does NOT exist

**Exchanges Tab:**
- ✅ `matches-fanout` has 2 bindings (local + dev)

## Rollback Plan

If you need to revert to the old setup:

```bash
# 1. Restore old RabbitMQ config from git history
git show HEAD~1:k3s/rabbitmq/configmap.yaml > rabbitmq-old.yaml
kubectl apply -f rabbitmq-old.yaml

# 2. Restart RabbitMQ
kubectl delete pod rabbitmq-0 -n match-scraper

# 3. Restore prod workers
kubectl apply -f k3s/workers/prod-deployment.yaml
kubectl apply -f k3s/workers/prod-configmap.yaml

# 4. Remove local workers
kubectl delete deployment missing-table-celery-worker-local -n match-scraper
kubectl delete configmap missing-table-worker-local-config -n match-scraper
```

## Environment URLs

| Environment | Public URL | Supabase Project | Worker Count |
|-------------|------------|------------------|--------------|
| **local** | N/A (local only) | Local Supabase | 1 |
| **dev** | https://missingtable.com | ppgxasqgqbnauvxozmjw | 2 |
| ~~**prod**~~ | ~~N/A~~ | ~~iueycteoamjbygwhnovz~~ | ~~Deprecated~~ |

## FAQ

### Q: Why remove prod?

**A:** missingtable.com now points to the dev environment. Maintaining a separate prod environment added complexity without benefit.

### Q: What happens to existing prod data?

**A:** The prod Supabase database remains accessible but is no longer receiving new matches. Prod workers have been shut down.

### Q: Can I still test locally?

**A:** Yes! The new `matches.local` queue routes to local workers for local development and testing.

### Q: Do I need to update match-scraper code?

**A:** No! The fanout exchange pattern automatically handles routing. No code changes needed.

### Q: What if dev goes down?

**A:** Messages will queue in `matches.dev` and process when workers come back online. RabbitMQ provides durability.

## Next Steps

1. ✅ Update RabbitMQ configuration
2. ✅ Deploy local workers (optional)
3. ✅ Remove prod workers
4. ✅ Verify fanout routing
5. ⬜ Monitor for 24 hours
6. ⬜ Update team documentation
7. ⬜ Clean up prod Supabase project (when ready)

## Support

If you encounter issues:
1. Check RabbitMQ logs: `kubectl logs rabbitmq-0 -n match-scraper`
2. Check worker logs: `kubectl logs -l app=missing-table-worker -n match-scraper`
3. Verify queue bindings in RabbitMQ UI
4. Consult [Async Message Queue Architecture](../architecture/async-message-queue-architecture.md)

---

**Migration completed:** 2025-11-14
**Tested by:** Match-scraper team
**Status:** ✅ Successful
