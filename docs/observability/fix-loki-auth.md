# Fix Loki Authentication Issue

## Current Status ✅

Your setup is **almost working**:
- ✅ Logs are being written to `/var/log/scraper/app.log`
- ✅ Promtail is reading the log file successfully
- ✅ Promtail is sending logs to Grafana Cloud
- ❌ **Authentication failing with 401 error**

## Problem

The token you're using (`GRAFANA_CLOUD_API_TOKEN`) is an **OTLP/Metrics token**, not a **Loki token**.

Error from Promtail logs:
```
status=401 error="authentication error: legacy auth cannot be upgraded because the host is not found"
```

## Solution: Get Loki API Token

You need to generate a **Loki-specific API token** from Grafana Cloud.

### Step 1: Get Your Loki Credentials

1. Go to [Grafana Cloud Portal](https://grafana.com)
2. Click on your stack
3. Click **"Send Logs"** or **"Loki"** in the left sidebar
4. Look for **"Loki Details"** or **"Configuration"**
5. You'll see:
   - **URL**: `https://logs-prod-XXX.grafana.net` (you already have this ✅)
   - **User/Instance ID**: Usually a number like `1184667` or `username`
   - **API Key/Token**: This is what you need!

### Step 2: Authentication Format

Grafana Cloud Loki uses **Basic Auth**, not Bearer tokens. The format is:

```
Username: <LOKI_USER_ID>
Password: <LOKI_API_KEY>
```

This is typically encoded as: `<USER_ID>:<API_KEY>` in base64.

### Step 3: Update Your Secret

You have two options:

#### Option A: Use Basic Auth (Recommended)

Update your secret with the Loki username and API key:

```bash
# Get your Loki User ID and API Key from Grafana Cloud
LOKI_USER_ID="1184667"  # Replace with your actual User ID
LOKI_API_KEY="glsa_xxxxxxxxxxxxx"  # Replace with your actual Loki API key

# Encode as Basic Auth
LOKI_AUTH=$(echo -n "${LOKI_USER_ID}:${LOKI_API_KEY}" | base64)

# Update the secret
kubectl create secret generic mls-scraper-secrets \
  -n match-scraper \
  --from-literal=MISSING_TABLE_API_TOKEN="$(kubectl get secret mls-scraper-secrets -n match-scraper -o jsonpath='{.data.MISSING_TABLE_API_TOKEN}' | base64 -d)" \
  --from-literal=OTEL_EXPORTER_OTLP_HEADERS="$(kubectl get secret mls-scraper-secrets -n match-scraper -o jsonpath='{.data.OTEL_EXPORTER_OTLP_HEADERS}' | base64 -d)" \
  --from-literal=GRAFANA_CLOUD_API_TOKEN="$LOKI_AUTH" \
  --dry-run=client -o yaml | kubectl apply -f -
```

#### Option B: Use the Grafana.com API Token

If you have a `grafana.com` API token with Logs:Write permissions:

```bash
# Your grafana.com API token
GRAFANA_COM_TOKEN="glc_xxxxxxxxxxxxx"  # Replace with actual token

# Update secret
kubectl patch secret mls-scraper-secrets -n match-scraper \
  --type=json \
  -p="[{\"op\": \"replace\", \"path\": \"/data/GRAFANA_CLOUD_API_TOKEN\", \"value\": \"$(echo -n "$GRAFANA_COM_TOKEN" | base64)\"}]"
```

### Step 4: Update Promtail Config

Update `k8s/promtail-config.yaml` to use Basic Auth:

```yaml
clients:
  - url: ${LOKI_ENDPOINT}
    basic_auth:
      username: ${LOKI_USER_ID}
      password: ${LOKI_API_KEY}
    batchwait: 1s
    batchsize: 1048576
    timeout: 10s
```

OR if using Bearer token format:

```yaml
clients:
  - url: ${LOKI_ENDPOINT}
    headers:
      Authorization: Basic ${GRAFANA_CLOUD_API_TOKEN}
    batchwait: 1s
    batchsize: 1048576
    timeout: 10s
```

### Step 5: Add Environment Variables to CronJob

Update `k8s/cronjob.yaml` to pass the credentials:

```yaml
- name: LOKI_USER_ID
  valueFrom:
    secretKeyRef:
      name: mls-scraper-secrets
      key: LOKI_USER_ID
- name: LOKI_API_KEY
  valueFrom:
    secretKeyRef:
      name: mls-scraper-secrets
      key: LOKI_API_KEY
```

### Step 6: Apply and Test

```bash
# Apply updated configs
kubectl apply -f k8s/secret.yaml
kubectl apply -f k8s/promtail-config.yaml
kubectl apply -f k8s/cronjob.yaml

# Run test
./scripts/trigger-scrape.sh -- --no-api --start 0 --end 0

# Check Promtail logs - should NOT see 401 errors
SHOW_PROMTAIL_LOGS=true ./scripts/trigger-scrape.sh -- --no-api --start 0 --end 0
```

## Quick Debug Commands

```bash
# Check current endpoint
kubectl get cm mls-scraper-config -n match-scraper -o jsonpath='{.data.LOKI_ENDPOINT}'

# Check token format
kubectl get secret mls-scraper-secrets -n match-scraper -o jsonpath='{.data.GRAFANA_CLOUD_API_TOKEN}' | base64 -d | head -c 20

# View Promtail logs
kubectl logs -n match-scraper <pod-name> -c promtail --tail=50

# Test authentication manually
LOKI_URL="https://logs-prod-036.grafana.net/loki/api/v1/push"
USER_ID="your-user-id"
API_KEY="your-api-key"

curl -v -X POST "$LOKI_URL" \
  -u "$USER_ID:$API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "streams": [
      {
        "stream": {"job": "test"},
        "values": [["'$(date +%s)000000000'", "test message"]]
      }
    ]
  }'
```

## Finding Your Loki Credentials

### Method 1: Grafana Cloud UI
1. Go to https://grafana.com
2. Select your stack
3. Click **Loki** or **Logs** in left menu
4. Click **"Configuration"** or **"Details"**
5. Copy the User ID and generate/copy API key

### Method 2: From Helm/Config
If you set up Grafana Cloud via Helm, check:
```bash
helm get values grafana-agent -n grafana-agent
```

### Method 3: Create New API Token
1. Go to https://grafana.com/orgs/<your-org>/access-policies
2. Click **"Create access policy"**
3. Select scopes: `logs:write`, `logs:read`
4. Click **"Create token"**
5. Copy the token (starts with `glsa_`)

## Verification

Once configured correctly, you should see in Promtail logs:
```
level=info msg="Successfully sent batch"
```

And in Grafana Explore:
```
{job="mls-match-scraper"} |= ""
```

Should return your application logs!
