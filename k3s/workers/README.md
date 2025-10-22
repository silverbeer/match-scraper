# Missing Table Celery Workers for K3s

This directory contains manifests for Celery workers that process match data from RabbitMQ and write to Supabase.

## Architecture

```
Match Scraper → matches-fanout exchange
                 ├→ matches.prod queue → Prod Workers → Prod Supabase
                 └→ matches.dev queue  → Dev Workers  → Dev Supabase
```

## Worker Types

### Development Workers (`dev-*`)
- **Queue**: `matches.dev`
- **Supabase**: Development instance (ppgxasqgqbnauvxozmjw)
- **Replicas**: 2
- **Purpose**: Testing and development

### Production Workers (`prod-*`)
- **Queue**: `matches.prod`
- **Supabase**: Production instance (requires configuration)
- **Replicas**: 2
- **Purpose**: Production data storage

## Setup Instructions

### 1. Deploy Development Workers

Development workers use existing secrets (`missing-table-worker-secrets`).

```bash
# Apply dev worker configuration
kubectl apply -f k3s/workers/dev-configmap.yaml
kubectl apply -f k3s/workers/dev-deployment.yaml

# Verify deployment
kubectl get pods -n match-scraper -l environment=dev
kubectl logs -n match-scraper -l environment=dev --tail=50
```

### 2. Deploy Production Workers

**Prerequisites**: Production Supabase credentials

**📖 See detailed credential guide: [docs/deployment/supabase-credentials.md](../../docs/deployment/supabase-credentials.md)**

```bash
# Step 1: Create prod secrets
cp k3s/workers/prod-secret.yaml.template k3s/workers/prod-secret.yaml

# Step 2: Edit prod-secret.yaml with your production credentials
# Follow the detailed guide: docs/deployment/supabase-credentials.md
# Quick reference:
#   - SUPABASE_KEY: Supabase Dashboard → Settings → API → service_role key
#   - SUPABASE_JWT_SECRET: Supabase Dashboard → Settings → API → JWT Secret
#   - SERVICE_ACCOUNT_SECRET: From your backend .env or existing dev secret
#
# Encode values: echo -n "your-value" | base64

# Step 3: Update Supabase URL in prod ConfigMap
# Edit k3s/workers/prod-configmap.yaml
# Replace: YOUR_PROD_SUPABASE_URL with actual prod URL

# Step 4: Apply prod worker configuration
kubectl apply -f k3s/workers/prod-secret.yaml
kubectl apply -f k3s/workers/prod-configmap.yaml
kubectl apply -f k3s/workers/prod-deployment.yaml

# Verify deployment
kubectl get pods -n match-scraper -l environment=prod
kubectl logs -n match-scraper -l environment=prod --tail=50
```

### 3. Remove Old Workers (Optional)

If you have the old unified worker deployment:

```bash
# Scale down old workers
kubectl scale deployment missing-table-celery-worker -n match-scraper --replicas=0

# Or delete entirely
kubectl delete deployment missing-table-celery-worker -n match-scraper
kubectl delete configmap missing-table-worker-config -n match-scraper
```

## Monitoring Workers

```bash
# Check worker status
kubectl get deployments -n match-scraper -l app=missing-table-worker

# View dev worker logs
kubectl logs -n match-scraper -l environment=dev -f

# View prod worker logs
kubectl logs -n match-scraper -l environment=prod -f

# Check queue status in RabbitMQ
kubectl exec -n match-scraper rabbitmq-0 -- rabbitmqctl list_queues name messages consumers

# Access RabbitMQ Management UI
# http://localhost:30672 (username: admin, password: admin123)
```

## Scaling Workers

```bash
# Scale dev workers
kubectl scale deployment missing-table-celery-worker-dev -n match-scraper --replicas=4

# Scale prod workers
kubectl scale deployment missing-table-celery-worker-prod -n match-scraper --replicas=4
```

## Troubleshooting

### Workers not consuming messages

```bash
# Check worker logs for errors
kubectl logs -n match-scraper -l environment=dev --tail=100

# Verify queue bindings in RabbitMQ
kubectl exec -n match-scraper rabbitmq-0 -- rabbitmqctl list_bindings

# Check if exchange exists
kubectl exec -n match-scraper rabbitmq-0 -- rabbitmqctl list_exchanges
```

### Connection issues

```bash
# Test RabbitMQ connectivity from worker pod
kubectl exec -n match-scraper deployment/missing-table-celery-worker-dev -- \
  curl -u admin:admin123 http://rabbitmq.match-scraper:15672/api/overview

# Check ConfigMap values
kubectl get configmap missing-table-worker-dev-config -n match-scraper -o yaml
```

### Supabase connection issues

```bash
# Check secret values (base64 encoded)
kubectl get secret missing-table-worker-prod-secrets -n match-scraper -o yaml

# Decode a secret value
kubectl get secret missing-table-worker-prod-secrets -n match-scraper \
  -o jsonpath='{.data.SUPABASE_KEY}' | base64 --decode
```

## Configuration Files

- `dev-configmap.yaml` - Dev worker environment variables
- `dev-deployment.yaml` - Dev worker deployment spec
- `prod-configmap.yaml` - Prod worker environment variables
- `prod-deployment.yaml` - Prod worker deployment spec
- `prod-secret.yaml.template` - Prod secrets template (copy and fill in)

## Security Notes

- **Never commit** `prod-secret.yaml` to git (already in .gitignore)
- Use base64 encoding for secret values: `echo -n "value" | base64`
- Rotate Supabase keys regularly
- Review worker resource limits based on actual usage
