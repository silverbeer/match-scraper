# GitHub Actions GKE Deployment Setup

This guide explains how to configure GitHub Actions to automatically deploy to GKE when changes are merged to `main`.

## Quick Start (Automated Setup)

**The fastest way to set up GitHub Actions for GKE deployment:**

```bash
# Run the automated setup script
./scripts/setup-github-actions-gcp.sh
```

This script will:
- ✅ Enable required GCP APIs
- ✅ Create service account with proper permissions
- ✅ Set up Workload Identity Federation
- ✅ Configure repository access
- ✅ Generate GitHub Secrets for you to copy

**Then follow the prompts and add the generated secrets to GitHub!**

---

## Overview

The `.github/workflows/gke-deploy.yml` workflow automatically:
1. ✅ Runs tests (linting + unit tests)
2. 🐳 Builds Docker image with the latest code
3. 📤 Pushes image to Google Container Registry (GCR)
4. 🚀 Deploys to your GKE cluster
5. ✅ Verifies deployment succeeded

## Prerequisites

1. **GKE Cluster** - Already created and running
2. **Google Cloud Project** - With billing enabled
3. **GitHub Repository** - This repository with admin access
4. **gcloud CLI** - Installed and authenticated (`gcloud auth login`)

---

## Manual Setup (if you prefer not to use the script)

## Step 1: Set Up GCP Service Account (Recommended Method)

### Option A: Workload Identity Federation (Most Secure - Recommended)

Workload Identity Federation allows GitHub Actions to authenticate without storing long-lived credentials.

#### 1.1 Enable Required APIs

```bash
gcloud services enable iamcredentials.googleapis.com \
  container.googleapis.com \
  cloudresourcemanager.googleapis.com \
  --project=YOUR_PROJECT_ID
```

#### 1.2 Create Service Account

```bash
# Set variables
export PROJECT_ID="YOUR_PROJECT_ID"
export PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format="value(projectNumber)")
export SERVICE_ACCOUNT_NAME="github-actions-gke"
export GITHUB_REPO="YOUR_GITHUB_USERNAME/match-scraper"

# Create service account
gcloud iam service-accounts create $SERVICE_ACCOUNT_NAME \
  --display-name="GitHub Actions GKE Deployer" \
  --project=$PROJECT_ID
```

#### 1.3 Grant Permissions

```bash
# Service account email
export SA_EMAIL="${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

# Grant necessary roles
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/container.developer"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/storage.admin"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/artifactregistry.writer"
```

#### 1.4 Create Workload Identity Pool

```bash
# Create workload identity pool
gcloud iam workload-identity-pools create "github-actions-pool" \
  --project=$PROJECT_ID \
  --location="global" \
  --display-name="GitHub Actions Pool"

# Get the pool ID
export WORKLOAD_IDENTITY_POOL_ID=$(gcloud iam workload-identity-pools describe "github-actions-pool" \
  --project=$PROJECT_ID \
  --location="global" \
  --format="value(name)")

echo "Workload Identity Pool ID: $WORKLOAD_IDENTITY_POOL_ID"
```

#### 1.5 Create Workload Identity Provider

```bash
# Create provider for GitHub
gcloud iam workload-identity-pools providers create-oidc "github-actions-provider" \
  --project=$PROJECT_ID \
  --location="global" \
  --workload-identity-pool="github-actions-pool" \
  --display-name="GitHub Actions Provider" \
  --attribute-mapping="google.subject=assertion.sub,attribute.actor=assertion.actor,attribute.repository=assertion.repository" \
  --issuer-uri="https://token.actions.githubusercontent.com"

# Get the provider name
export WORKLOAD_IDENTITY_PROVIDER=$(gcloud iam workload-identity-pools providers describe "github-actions-provider" \
  --project=$PROJECT_ID \
  --location="global" \
  --workload-identity-pool="github-actions-pool" \
  --format="value(name)")

echo "Workload Identity Provider: $WORKLOAD_IDENTITY_PROVIDER"
```

#### 1.6 Allow GitHub Actions to Impersonate Service Account

```bash
# Allow GitHub repo to impersonate the service account
gcloud iam service-accounts add-iam-policy-binding $SA_EMAIL \
  --project=$PROJECT_ID \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/${WORKLOAD_IDENTITY_POOL_ID}/attribute.repository/${GITHUB_REPO}"
```

#### 1.7 Save Values for GitHub Secrets

```bash
# Print values to add to GitHub Secrets
echo "================================================"
echo "Add these to GitHub Repository Secrets:"
echo "================================================"
echo "GCP_PROJECT_ID: $PROJECT_ID"
echo "GCP_SERVICE_ACCOUNT: $SA_EMAIL"
echo "GCP_WORKLOAD_IDENTITY_PROVIDER: $WORKLOAD_IDENTITY_PROVIDER"
echo "================================================"
```

### Option B: Service Account Key (Less Secure - Not Recommended)

<details>
<summary>Click to expand alternative method using service account keys</summary>

This method is simpler but less secure as it requires storing long-lived credentials.

```bash
# Create service account key
gcloud iam service-accounts keys create github-actions-key.json \
  --iam-account=$SA_EMAIL

# Base64 encode the key
cat github-actions-key.json | base64

# Add this to GitHub Secret: GCP_SERVICE_ACCOUNT_KEY
# Then delete the local key file!
rm github-actions-key.json
```

Note: If using this method, you'll need to modify the workflow to use `google-github-actions/auth@v2` with `credentials_json` instead of `workload_identity_provider`.

</details>

## Step 2: Configure GitHub Secrets

Go to your GitHub repository:
1. Navigate to **Settings** → **Secrets and variables** → **Actions**
2. Click **New repository secret**
3. Add the following secrets:

| Secret Name | Description | Example Value |
|-------------|-------------|---------------|
| `GCP_PROJECT_ID` | Your GCP project ID | `missing-table-prod` |
| `GCP_SERVICE_ACCOUNT` | Service account email | `github-actions-gke@missing-table-prod.iam.gserviceaccount.com` |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | Full workload identity provider name | `projects/123456789/locations/global/workloadIdentityPools/github-actions-pool/providers/github-actions-provider` |

### Verifying Secrets

After adding secrets, you should see them listed (values hidden) in your repository settings.

## Step 3: Update Workflow Configuration (Optional)

The workflow includes some default values that you may want to customize:

```yaml
env:
  GCP_REGION: us-central1          # Your GCP region
  GKE_CLUSTER: missing-table-dev   # Your GKE cluster name
  GKE_ZONE: us-central1            # Your GKE cluster zone/region
  NAMESPACE: match-scraper         # Kubernetes namespace
```

**Note:** The current cluster is a **regional cluster** (not zonal), so the workflow uses `--region` instead of `--zone`.

Edit `.github/workflows/gke-deploy.yml` if your values differ.

## Step 4: Create Required Kubernetes Secrets

The workflow expects certain secrets to exist in your GKE cluster. Create them if they don't exist:

```bash
# Get cluster credentials
gcloud container clusters get-credentials YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --project YOUR_PROJECT_ID

# Create namespace
kubectl apply -f k8s/namespace.yaml

# Create secrets (replace with your actual values)
kubectl create secret generic mls-scraper-secrets \
  -n match-scraper \
  --from-literal=MISSING_TABLE_API_TOKEN='your-api-token-here' \
  --from-literal=OTEL_EXPORTER_OTLP_HEADERS='your-base64-encoded-otlp-headers' \
  --from-literal=LOKI_USER_ID='your-grafana-loki-user-id' \
  --from-literal=LOKI_API_KEY='your-grafana-loki-api-key'

# Verify secrets were created
kubectl get secrets -n match-scraper
```

## Step 5: Test the Workflow

### Automatic Trigger

The workflow automatically runs when:
- Code is pushed to `main` branch
- Changes are made to: `src/`, `k8s/`, `Dockerfile.gke`, `pyproject.toml`, or `uv.lock`

### Manual Trigger

You can also trigger the workflow manually:

1. Go to **Actions** tab in GitHub
2. Select **Deploy to GKE** workflow
3. Click **Run workflow**
4. Choose whether to skip tests (optional)
5. Click **Run workflow** button

### Monitor the Workflow

1. Go to **Actions** tab
2. Click on the running workflow
3. Watch the progress in real-time
4. Check the deployment summary at the bottom

## Step 6: Verify Deployment

After the workflow completes:

```bash
# Check CronJob status
kubectl get cronjob -n match-scraper

# View recent jobs
kubectl get jobs -n match-scraper --sort-by=.metadata.creationTimestamp

# Check logs
kubectl logs -n match-scraper -l app=mls-scraper --tail=100

# Trigger a test run
kubectl create job --from=cronjob/mls-scraper-cronjob manual-test-$(date +%s) -n match-scraper

# Watch the test job
kubectl get pods -n match-scraper -w
```

## Troubleshooting

### Authentication Failed

**Error:** "Unable to authenticate to Google Cloud"

**Solution:**
1. Verify service account has correct permissions
2. Check that Workload Identity Provider is configured correctly
3. Ensure GitHub repo name in IAM policy matches exactly

### Image Push Failed

**Error:** "Access denied to gcr.io"

**Solution:**
1. Ensure service account has `roles/storage.admin` or `roles/artifactregistry.writer`
2. Enable Container Registry API in GCP
3. Verify Docker authentication is configured

### Deployment Failed

**Error:** "Unable to connect to GKE cluster"

**Solution:**
1. Verify cluster name and zone are correct in workflow
2. Check service account has `roles/container.developer`
3. Ensure cluster exists and is running

### Secrets Missing

**Error:** "Secret mls-scraper-secrets does not exist"

**Solution:**
Create the secret manually (see Step 4 above)

## Rollback

If deployment fails or introduces issues:

```bash
# List recent images
gcloud container images list-tags gcr.io/YOUR_PROJECT_ID/mls-scraper

# Rollback to previous image
kubectl set image cronjob/mls-scraper-cronjob \
  mls-scraper=gcr.io/YOUR_PROJECT_ID/mls-scraper:PREVIOUS_TAG \
  -n match-scraper

# Verify rollback
kubectl describe cronjob mls-scraper-cronjob -n match-scraper
```

## Security Best Practices

1. ✅ **Use Workload Identity Federation** (not service account keys)
2. ✅ **Limit service account permissions** to only what's needed
3. ✅ **Rotate secrets regularly** in Kubernetes
4. ✅ **Enable branch protection** on `main` branch
5. ✅ **Require PR reviews** before merging to `main`
6. ✅ **Use dependabot** to keep GitHub Actions up to date

## Monitoring

After deployment, monitor:

1. **GitHub Actions logs** - For deployment status
2. **GKE Workload logs** - `kubectl logs -n match-scraper -l app=mls-scraper`
3. **Grafana Loki** - For structured application logs
4. **Grafana Cloud Metrics** - For OpenTelemetry metrics

## Next Steps

1. ✅ Set up branch protection rules on `main`
2. ✅ Configure Slack/email notifications for workflow failures
3. ✅ Set up staging environment for testing before production
4. ✅ Implement deployment approvals for production deployments

## Resources

- [GitHub Actions with GCP](https://github.com/google-github-actions/auth)
- [Workload Identity Federation](https://cloud.google.com/iam/docs/workload-identity-federation)
- [GKE Best Practices](https://cloud.google.com/kubernetes-engine/docs/best-practices)
- [GitHub Actions Security](https://docs.github.com/en/actions/security-guides)
