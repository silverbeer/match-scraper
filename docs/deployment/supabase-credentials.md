# Getting Supabase Credentials for Production Workers

This guide explains how to find and configure Supabase credentials for the production workers.

## Required Credentials

For production workers, you need three secrets:

1. **SUPABASE_KEY** (service_role key) - **REQUIRED**
2. **SUPABASE_JWT_SECRET** - **REQUIRED**
3. **SERVICE_ACCOUNT_SECRET** - **OPTIONAL** (only if your backend uses it)

## Step-by-Step Guide

### 1. Access Your Supabase Dashboard

1. Go to https://supabase.com
2. Sign in to your account
3. Select your **production** project (not dev!)
4. You should see your project dashboard

### 2. Get SUPABASE_KEY (service_role key)

**What it is:** This is the service role API key that bypasses Row Level Security (RLS) policies. It's used by backend services to write data directly to the database.

**How to find it:**

1. In your Supabase project dashboard, click **Settings** (gear icon) in the left sidebar
2. Click **API** under "Project Settings"
3. Scroll down to the **Project API keys** section
4. Look for **`service_role`** key (NOT the `anon` key!)

   ```
   Project API keys
   ├─ anon public          eyJhbGc... (don't use this one)
   └─ service_role secret  eyJhbGc... ← USE THIS ONE
   ```

5. Click the **copy** icon next to the `service_role` key
6. This is your `SUPABASE_KEY` value

**⚠️ Important:**
- Use `service_role`, NOT `anon`
- This key is sensitive - never commit it to git!
- It should start with `eyJ...`

### 3. Get SUPABASE_JWT_SECRET

**What it is:** The secret used to sign and verify JWT tokens. Your backend needs this to validate auth tokens.

**How to find it:**

1. Still in **Settings → API**
2. Scroll down to the **JWT Settings** section
3. Look for **`JWT Secret`**

   ```
   JWT Settings
   ├─ JWT Secret: super-secret-jwt-token-with-at-least-32-characters-long
   └─ JWT expiry limit: 3600
   ```

4. Click the **copy** icon or select and copy the JWT Secret
5. This is your `SUPABASE_JWT_SECRET` value

**⚠️ Important:**
- This is different from the service_role key
- It's usually a long random string
- Also keep this secret!

### 4. Get SERVICE_ACCOUNT_SECRET (Optional)

**What it is:** A custom secret specific to your backend application. This might be used for additional authentication or encryption.

**How to find it:**

This depends on your backend implementation:

#### Option A: Check your missing-table backend code

Look in your missing-table backend repository:

```bash
cd /path/to/missing-table
grep -r "SERVICE_ACCOUNT_SECRET" .
```

If you find references, check:
- Environment variable files (`.env.example`, `.env.production`)
- Configuration files
- Documentation

#### Option B: Check existing dev workers

If you already have dev workers running, you can see what value they use:

```bash
# Get the secret from dev workers
kubectl get secret missing-table-worker-secrets -n match-scraper -o yaml

# Decode the value
kubectl get secret missing-table-worker-secrets -n match-scraper \
  -o jsonpath='{.data.SERVICE_ACCOUNT_SECRET}' | base64 --decode
```

#### Option C: It might not be needed

If your backend doesn't use `SERVICE_ACCOUNT_SECRET`, you can set it to an empty value or the same as one of the other secrets.

## Encoding the Secrets

Kubernetes secrets must be base64-encoded. Here's how:

### On macOS/Linux:

```bash
# Encode SUPABASE_KEY
echo -n "your-actual-service-role-key-here" | base64

# Encode SUPABASE_JWT_SECRET
echo -n "your-actual-jwt-secret-here" | base64

# Encode SERVICE_ACCOUNT_SECRET
echo -n "your-actual-service-account-secret-here" | base64
```

**⚠️ Important:** Use `echo -n` (with `-n` flag) to avoid encoding a trailing newline!

### Example:

```bash
# Input
echo -n "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InBwZ3hhc3FncWJuYXV2eG96bWp3Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTYzMDU0MTc4MiwiZXhwIjoxOTQ2MTE3NzgyfQ.abc123" | base64

# Output (base64-encoded)
ZXlKaGJHY2lPaUpJVXpJMU5pSXNJblI1Y0NJNklrcFhWQ0o5LmV5SnBjM01pT2lKemRYQmhZbUZ6WlNJc0luSmxaaUk2SW5Cd1ozeGhjM0ZuY1dKdVlYVjJlRzk2YldwM0lpd2ljbTlzWlNJNkluTmxjblpwWTJWZmNtOXNaU0lzSW1saGRDSTZNVFl6TURVME1UYzRNaXdpWlhod0lqb3hPVFEyTVRFM056Z3lmUS5hYmMxMjM=
```

## Creating the Production Secret File

1. **Copy the template:**
   ```bash
   cd k3s/workers
   cp prod-secret.yaml.template prod-secret.yaml
   ```

2. **Edit the file:**
   ```bash
   nano prod-secret.yaml  # or use your preferred editor
   ```

3. **Replace placeholders with base64-encoded values:**

   ```yaml
   apiVersion: v1
   kind: Secret
   metadata:
     name: missing-table-worker-prod-secrets
     namespace: match-scraper
     labels:
       app: missing-table-worker
       environment: prod
   type: Opaque
   data:
     # Replace with your base64-encoded service_role key
     SUPABASE_KEY: "ZXlKaGJHY2lPaUpJVXpJMU5pSXNJblI..."

     # Replace with your base64-encoded JWT secret
     SUPABASE_JWT_SECRET: "c3VwZXItc2VjcmV0LWp3dC10b2tlbi13aXRo..."

     # Replace with your base64-encoded service account secret
     SERVICE_ACCOUNT_SECRET: "bXktc2VydmljZS1hY2NvdW50LXNlY3JldA=="
   ```

4. **Save and close** the file

## Verify Your Secrets

Before deploying, verify the values decode correctly:

```bash
# Test decode SUPABASE_KEY
echo "ZXlKaGJHY2lPaUpJVXpJMU5pSXNJblI..." | base64 --decode
# Should output your service_role key starting with eyJ...

# Test decode SUPABASE_JWT_SECRET
echo "c3VwZXItc2VjcmV0LWp3dC10b2tlbi13aXRo..." | base64 --decode
# Should output your JWT secret

# Test decode SERVICE_ACCOUNT_SECRET
echo "bXktc2VydmljZS1hY2NvdW50LXNlY3JldA==" | base64 --decode
# Should output your service account secret
```

## Deploy the Secret

Once you've filled in all values:

```bash
# Apply the secret
kubectl apply -f k3s/workers/prod-secret.yaml

# Verify it was created
kubectl get secret missing-table-worker-prod-secrets -n match-scraper

# Check the keys exist (values will be hidden)
kubectl describe secret missing-table-worker-prod-secrets -n match-scraper
```

Expected output:
```
Name:         missing-table-worker-prod-secrets
Namespace:    match-scraper
Labels:       app=missing-table-worker
              environment=prod

Type:  Opaque

Data
====
SERVICE_ACCOUNT_SECRET:  32 bytes
SUPABASE_JWT_SECRET:     45 bytes
SUPABASE_KEY:            218 bytes
```

## Common Issues

### Issue: "invalid base64 data"

**Cause:** Trailing newline was encoded

**Fix:** Use `echo -n` (with `-n` flag):
```bash
# Wrong (includes newline)
echo "my-secret" | base64

# Correct (no newline)
echo -n "my-secret" | base64
```

### Issue: Workers can't connect to Supabase

**Cause:** Wrong key type (using `anon` instead of `service_role`)

**Fix:** Go back to Supabase dashboard and copy the `service_role` key, not `anon`

### Issue: "The JWT Secret is not set"

**Cause:** JWT secret is missing or incorrect

**Fix:**
1. Double-check you copied the JWT Secret from **Settings → API → JWT Settings**
2. Re-encode and update the secret

## Security Best Practices

1. **Never commit secrets to git**
   - `prod-secret.yaml` is already in `.gitignore`
   - Keep it that way!

2. **Rotate secrets regularly**
   - Change JWT secret periodically
   - Regenerate service_role key if compromised

3. **Use different credentials for dev and prod**
   - Dev workers should use dev Supabase project
   - Prod workers should use prod Supabase project
   - Never mix them!

4. **Limit access**
   - Only people who need prod access should have these secrets
   - Store them in a password manager
   - Don't share via email/Slack

## Next Steps

After creating the secret:

1. Update the prod ConfigMap with your prod Supabase URL:
   ```bash
   nano k3s/workers/prod-configmap.yaml
   # Replace: YOUR_PROD_SUPABASE_URL
   ```

2. Deploy prod workers:
   ```bash
   ./scripts/deploy-k3s.sh --deploy-workers
   ```

3. Verify workers are running:
   ```bash
   kubectl get pods -n match-scraper -l environment=prod
   kubectl logs -n match-scraper -l environment=prod --tail=50
   ```

## Reference

- **Supabase Docs:** https://supabase.com/docs/guides/api/api-keys
- **JWT Docs:** https://supabase.com/docs/guides/auth/server-side/jwt
- **Kubernetes Secrets:** https://kubernetes.io/docs/concepts/configuration/secret/
