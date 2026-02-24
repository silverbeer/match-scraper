# Missing Table Celery Workers for K3s

This directory contains manifests for Celery workers that process match data from RabbitMQ and write to Supabase. All workers run on the M4 Mac in rancher-desktop K3s alongside the rest of the scraper pipeline.

## Architecture

```
Match Scraper Agent → matches-fanout exchange
                       ├→ matches.prod queue  → Prod Workers  → Prod Supabase (missingtable.com)
                       └→ matches.local queue → Local Workers → Local Supabase (localhost:54321)
```

**Environments**: Prod and local only. There is no dev environment.

## Worker Types

### Production Workers (`prod-*`)
- **Queue**: `matches.prod`
- **Supabase**: Prod instance (`ppgxasqgqbnauvxozmjw`) — serves missingtable.com
- **Replicas**: 2
- **Purpose**: Production data storage

### Local Workers (`local-*`)
- **Queue**: `matches.local`
- **Supabase**: Local instance (`localhost:54321`)
- **Replicas**: 1
- **Purpose**: Local development and testing

## Setup Instructions

### 1. Deploy Production Workers

Production workers use existing secrets (`missing-table-worker-secrets`).

```bash
# Apply prod worker configuration
kubectl apply -f k3s/workers/prod-configmap.yaml
kubectl apply -f k3s/workers/prod-deployment.yaml

# Verify deployment
kubectl get pods -n match-scraper -l environment=prod
kubectl logs -n match-scraper -l environment=prod --tail=50
```

### 2. Deploy Local Workers (Optional)

```bash
# Apply local worker configuration
kubectl apply -f k3s/workers/local-configmap.yaml
kubectl apply -f k3s/workers/local-deployment.yaml

# Verify deployment
kubectl get pods -n match-scraper -l environment=local
kubectl logs -n match-scraper -l environment=local --tail=50
```

## Monitoring Workers

```bash
# Check worker status
kubectl get deployments -n match-scraper -l app=missing-table-worker

# View prod worker logs
kubectl logs -n match-scraper -l environment=prod -f

# View local worker logs
kubectl logs -n match-scraper -l environment=local -f

# Check queue status in RabbitMQ
kubectl exec -n match-scraper rabbitmq-0 -- rabbitmqctl list_queues name messages consumers

# Access RabbitMQ Management UI
# http://localhost:30672 (username: admin, password: admin123)
```

## Scaling Workers

```bash
# Scale prod workers
kubectl scale deployment missing-table-celery-worker-prod -n match-scraper --replicas=4

# Scale local workers
kubectl scale deployment missing-table-celery-worker-local -n match-scraper --replicas=2
```

## Troubleshooting

### Workers not consuming messages

```bash
# Check worker logs for errors
kubectl logs -n match-scraper -l environment=prod --tail=100

# Verify queue bindings in RabbitMQ
kubectl exec -n match-scraper rabbitmq-0 -- rabbitmqctl list_bindings

# Check if exchange exists
kubectl exec -n match-scraper rabbitmq-0 -- rabbitmqctl list_exchanges
```

### Connection issues

```bash
# Test RabbitMQ connectivity from worker pod
kubectl exec -n match-scraper deployment/missing-table-celery-worker-prod -- \
  curl -u admin:admin123 http://rabbitmq.match-scraper:15672/api/overview

# Check ConfigMap values
kubectl get configmap missing-table-worker-prod-config -n match-scraper -o yaml
```

## Configuration Files

- `prod-configmap.yaml` - Prod worker environment variables
- `prod-deployment.yaml` - Prod worker deployment spec
- `local-configmap.yaml` - Local worker environment variables
- `local-deployment.yaml` - Local worker deployment spec
- `prod-secret.yaml.template` - Prod secrets template (copy and fill in)

## Security Notes

- **Never commit** `prod-secret.yaml` to git (already in .gitignore)
- Use base64 encoding for secret values: `echo -n "value" | base64`
- Rotate Supabase keys regularly
- Review worker resource limits based on actual usage
