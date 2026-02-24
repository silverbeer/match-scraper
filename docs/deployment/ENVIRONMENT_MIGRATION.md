# Environment History & Queue Migration

**Last Updated:** 2026-02-23

## Current State

Two environments only: **prod** and **local**. There is no dev environment.

### Queue Layout

```
matches-fanout exchange
  ├─→ matches.prod queue  → Prod Workers → Prod Supabase (missingtable.com)
  └─→ matches.local queue → Local Workers → Local Supabase (localhost:54321)
```

### Worker Deployments

| Environment | Queue | Supabase | Status |
|-------------|-------|----------|--------|
| **prod** | `matches.prod` | `ppgxasqgqbnauvxozmjw.supabase.co` (missingtable.com) | Active |
| **local** | `matches.local` | `localhost:54321` | Active |

### Where Things Run

All scraper pipeline components (agent, RabbitMQ, Celery workers, iron-claw) run on the **M4 Mac in rancher-desktop K3s**. The missing-table API and frontend run in **cloud K8s**.

---

## Migration History

### 2025-11-14: Prod → Dev consolidation

The original `matches.prod` queue (pointing to the old Supabase project `iueycteoamjbygwhnovz`) was deprecated. Production traffic moved to the `matches.dev` queue which pointed to the Supabase project `ppgxasqgqbnauvxozmjw` serving missingtable.com. A `matches.local` queue was added for local development.

### 2026-02-23: Dev → Prod rename

The misleading `matches.dev` queue was renamed to `matches.prod` to accurately reflect that it writes to the production Supabase instance serving missingtable.com. The old "dev" worker manifests were replaced with properly named "prod" manifests. There is no dev Supabase — only prod and local.

---

## Verify Current Setup

```bash
# Check RabbitMQ queues
kubectl exec -n match-scraper rabbitmq-0 -- \
  rabbitmqctl list_queues name messages consumers

# Expected output:
# matches.prod     0    2    # 2 prod workers
# matches.local    0    1    # 1 local worker

# Check bindings
kubectl exec -n match-scraper rabbitmq-0 -- \
  rabbitmqctl list_bindings

# Expected:
# matches-fanout → matches.prod
# matches-fanout → matches.local
```
