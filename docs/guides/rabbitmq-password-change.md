# RabbitMQ Password Change Guide

This guide documents how to change the RabbitMQ password in your local k3s deployment.

## Overview

The default RabbitMQ password is `admin123` for local development. While this is acceptable for local-only deployments, you may want to change it to eliminate security warnings or follow security best practices.

## Current Password Locations

The password `admin123` appears in **10 files** across the codebase:

### K8s Manifests (5 files)

1. **`k3s/rabbitmq/secret.yaml`**
   - Line 15: Base64-encoded password in `rabbitmq-password` field
   - Current value: `YWRtaW4xMjM=` (base64 for `admin123`)

2. **`k3s/rabbitmq/configmap.yaml`**
   - Line 15: `default_pass = admin123`

3. **`k3s/match-scraper/configmap.yaml`**
   - Line 14: `RABBITMQ_URL: "amqp://admin:admin123@rabbitmq.match-scraper:5672//"`

4. **`k3s/workers/dev-configmap.yaml`**
   - Line 11: `CELERY_BROKER_URL: "amqp://admin:admin123@rabbitmq.match-scraper:5672//"`
   - Line 15: `RABBITMQ_URL: "amqp://admin:admin123@rabbitmq.match-scraper:5672//"`

5. **`k3s/workers/prod-configmap.yaml`**
   - Line 11: `CELERY_BROKER_URL: "amqp://admin:admin123@rabbitmq.match-scraper:5672//"`
   - Line 15: `RABBITMQ_URL: "amqp://admin:admin123@rabbitmq.match-scraper:5672//"`

### Scripts (2 files)

6. **`scripts/test-k3s.sh`**
   - Line 206: Manual job RABBITMQ_URL value
   - Line 387: Connection info documentation

7. **`scripts/deploy-k3s.sh`**
   - May reference password in helpful output sections

### Documentation (3 files)

8. **`docs/architecture/rabbitmq-fanout-dev-prod.md`**
9. **`docs/architecture/async-message-queue-architecture.md`**
10. **`docs/deployment/k3s-deployment.md`**

## Step-by-Step Password Change Process

### Step 1: Generate Base64-Encoded Password

First, decide on your new password and encode it:

```bash
# Replace YOUR_NEW_PASSWORD with your chosen password
echo -n "YOUR_NEW_PASSWORD" | base64
```

Save this base64 value - you'll need it for the secret file.

### Step 2: Update K8s Manifests

Update all 5 Kubernetes manifest files:

#### 2.1 Update `k3s/rabbitmq/secret.yaml`

```yaml
data:
  rabbitmq-username: YWRtaW4=
  rabbitmq-password: <YOUR_BASE64_PASSWORD>  # Replace with your base64 value
  rabbitmq-erlang-cookie: c2VjcmV0LWNvb2tpZS1mb3ItY2x1c3Rlcg==
```

#### 2.2 Update `k3s/rabbitmq/configmap.yaml`

```yaml
rabbitmq.conf: |
  # Default user configuration
  default_user = admin
  default_pass = YOUR_NEW_PASSWORD  # Replace with plaintext password
```

#### 2.3 Update `k3s/match-scraper/configmap.yaml`

```yaml
data:
  RABBITMQ_URL: "amqp://admin:YOUR_NEW_PASSWORD@rabbitmq.match-scraper:5672//"
```

#### 2.4 Update `k3s/workers/dev-configmap.yaml`

```yaml
data:
  CELERY_BROKER_URL: "amqp://admin:YOUR_NEW_PASSWORD@rabbitmq.match-scraper:5672//"
  RABBITMQ_URL: "amqp://admin:YOUR_NEW_PASSWORD@rabbitmq.match-scraper:5672//"
```

#### 2.5 Update `k3s/workers/prod-configmap.yaml`

```yaml
data:
  CELERY_BROKER_URL: "amqp://admin:YOUR_NEW_PASSWORD@rabbitmq.match-scraper:5672//"
  RABBITMQ_URL: "amqp://admin:YOUR_NEW_PASSWORD@rabbitmq.match-scraper:5672//"
```

### Step 3: Update Scripts

Update script files that reference the password:

#### 3.1 Update `scripts/test-k3s.sh`

Find and replace both occurrences:
- Line ~206: Job manifest RABBITMQ_URL
- Line ~387: Connection info display

```bash
# Change from:
value: "amqp://admin:admin123@rabbitmq.match-scraper:5672//"
# To:
value: "amqp://admin:YOUR_NEW_PASSWORD@rabbitmq.match-scraper:5672//"
```

#### 3.2 Update `scripts/deploy-k3s.sh`

Update any helpful output sections that display the password.

### Step 4: Update Documentation

Update the 3 documentation files that reference the password:

1. `docs/architecture/rabbitmq-fanout-dev-prod.md`
2. `docs/architecture/async-message-queue-architecture.md`
3. `docs/deployment/k3s-deployment.md`

Replace `admin123` with your new password in all examples and connection strings.

### Step 5: Apply Changes to K8s Cluster

Now redeploy RabbitMQ with the new password:

```bash
# 1. Delete the existing RabbitMQ pod to force recreation
kubectl delete pod rabbitmq-0 -n match-scraper

# 2. Apply updated ConfigMap
kubectl apply -f k3s/rabbitmq/configmap.yaml

# 3. Apply updated Secret
kubectl apply -f k3s/rabbitmq/secret.yaml

# 4. Wait for RabbitMQ to be ready (may take 60-90 seconds)
kubectl wait --for=condition=ready pod/rabbitmq-0 -n match-scraper --timeout=120s

# 5. Apply updated scraper ConfigMap
kubectl apply -f k3s/match-scraper/configmap.yaml

# 6. Apply updated worker ConfigMaps
kubectl apply -f k3s/workers/dev-configmap.yaml
kubectl apply -f k3s/workers/prod-configmap.yaml

# 7. Restart workers to pick up new credentials
kubectl rollout restart deployment missing-table-celery-worker-dev -n match-scraper
kubectl rollout restart deployment missing-table-celery-worker-prod -n match-scraper
```

### Step 6: Verify the Change

#### 6.1 Test RabbitMQ Management UI

Access the RabbitMQ management UI and login with new credentials:

```
URL: http://localhost:30672
Username: admin
Password: YOUR_NEW_PASSWORD
```

#### 6.2 Check RabbitMQ Pod Logs

```bash
kubectl logs rabbitmq-0 -n match-scraper --tail=50
```

Look for successful startup without authentication errors.

#### 6.3 Verify Worker Connections

```bash
kubectl logs -n match-scraper -l app=missing-table-worker --tail=20
```

Workers should show successful Celery broker connections.

#### 6.4 Test with Manual Job

Trigger a test scraper job to ensure end-to-end connectivity:

```bash
./scripts/test-k3s.sh trigger -a U14 -d Northeast

# Watch the logs
./scripts/test-k3s.sh logs -f
```

#### 6.5 Check RabbitMQ Queues

Verify messages are flowing through:

```bash
./scripts/test-k3s.sh rabbitmq
```

You should see:
- Exchanges configured (matches-fanout)
- Queues created (matches.dev, matches.prod)
- Messages being consumed by workers

## Security Best Practices

### For Local Development

While `admin123` is acceptable for local-only k3s clusters that are not exposed to the network, consider:

1. **Use a stronger password** if your development machine is on a shared network
2. **Never commit real credentials** - the current files are templates for local dev
3. **Keep the password in a secure location** (password manager)

### For Production/Shared Environments

If deploying to a shared cluster or production:

1. **Use strong random passwords** (20+ characters, mixed case, numbers, special chars)
2. **Use Kubernetes Secrets** instead of ConfigMaps for RABBITMQ_URL
3. **Enable TLS** for RabbitMQ connections (use `amqps://` instead of `amqp://`)
4. **Rotate passwords regularly** (quarterly or after any security incident)
5. **Use RBAC** to limit who can read secrets in the cluster
6. **Consider using a secrets manager** (HashiCorp Vault, Sealed Secrets, etc.)

## Generating Secure Passwords

To generate a secure random password:

```bash
# Generate a 24-character random password
openssl rand -base64 24

# Or using /dev/urandom
LC_ALL=C tr -dc 'A-Za-z0-9!@#$%^&*' < /dev/urandom | head -c 24 && echo
```

## Troubleshooting

### Workers Can't Connect

**Symptoms:**
- Workers showing "Connection refused" or authentication errors
- Celery broker connection failures

**Solution:**
1. Verify all ConfigMaps have been updated with new password
2. Restart worker deployments: `kubectl rollout restart deployment -l app=missing-table-worker -n match-scraper`
3. Check worker logs for specific error messages

### Management UI Login Fails

**Symptoms:**
- Cannot login to http://localhost:30672

**Solution:**
1. Verify `k3s/rabbitmq/secret.yaml` has correct base64-encoded password
2. Verify `k3s/rabbitmq/configmap.yaml` has correct plaintext password
3. Delete and recreate RabbitMQ pod: `kubectl delete pod rabbitmq-0 -n match-scraper`

### Scraper Jobs Fail

**Symptoms:**
- Manual jobs fail with connection errors

**Solution:**
1. Check `k3s/match-scraper/configmap.yaml` RABBITMQ_URL
2. Check `scripts/test-k3s.sh` line 206 for manual job password
3. Re-run deployment: `./scripts/deploy-k3s.sh --skip-build`

### RabbitMQ Pod Won't Start

**Symptoms:**
- Pod stuck in CrashLoopBackOff
- Logs show authentication or configuration errors

**Solution:**
1. Ensure `default_pass` in configmap matches password in secret
2. Check for typos in base64 encoding
3. Verify no special characters that need escaping in AMQP URLs

## Rollback Procedure

If you need to rollback to `admin123`:

```bash
# 1. Revert all files using git
git checkout HEAD -- k3s/rabbitmq/secret.yaml
git checkout HEAD -- k3s/rabbitmq/configmap.yaml
git checkout HEAD -- k3s/match-scraper/configmap.yaml
git checkout HEAD -- k3s/workers/dev-configmap.yaml
git checkout HEAD -- k3s/workers/prod-configmap.yaml
git checkout HEAD -- scripts/test-k3s.sh

# 2. Redeploy
./scripts/deploy-k3s.sh --skip-build

# 3. Restart workers
kubectl rollout restart deployment -l app=missing-table-worker -n match-scraper
```

## Notes

- **GKE Deployments**: The file `scripts/update-gke-secret.sh` references a different RabbitMQ instance in GKE, not your local k3s cluster
- **Persistence**: If you delete the RabbitMQ StatefulSet's PVC, you'll need to recreate exchanges/queues defined in the ConfigMap
- **Username**: This guide assumes you're keeping the username as `admin`. To change the username, update `rabbitmq-username` in the secret and `default_user` in the configmap

## Related Documentation

- [K3s Deployment Guide](../deployment/k3s-deployment.md)
- [RabbitMQ Fanout Architecture](../architecture/rabbitmq-fanout-dev-prod.md)
- [Async Message Queue Architecture](../architecture/async-message-queue-architecture.md)
