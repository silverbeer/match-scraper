# GKE Deployment Guide

This guide covers deploying the MLS Match Scraper to Google Kubernetes Engine (GKE) as a CronJob.

## Prerequisites

1. **GCP Project Setup**:
   - GCP project with billing enabled
   - GKE cluster (Autopilot recommended)
   - Container Registry enabled
   - `gcloud` CLI installed and authenticated

2. **Local Tools**:
   - `kubectl` configured to connect to your GKE cluster
   - `docker` installed
   - `gcloud` CLI authenticated

3. **API Access**:
   - Missing Table API token for data submission

## Quick Start

### Option 1: Complete Automated Deployment (Recommended)

#### Using terraform/dev.tfvars (Default)
```bash
# This script reads from terraform/dev.tfvars and handles everything
./scripts/deploy-gke-complete.sh
```

#### Using .env.dev file
```bash
# First, create your environment file
cp env.dev.template .env.dev
# Edit .env.dev with your values

# Then run the complete deployment
./scripts/deploy-gke-env.sh .env.dev
```

### Option 2: Step-by-Step Deployment

#### 1. Build and Push Container Image
```bash
# Replace YOUR_PROJECT_ID with your actual GCP project ID
./scripts/build-and-push-gke.sh YOUR_PROJECT_ID
```

#### 2. Deploy to GKE
```bash
# Replace YOUR_PROJECT_ID and YOUR_API_TOKEN with actual values
./scripts/deploy-to-gke.sh YOUR_PROJECT_ID YOUR_API_TOKEN
```

#### 3. Test the Deployment
```bash
# Trigger a test run
./scripts/test-gke.sh trigger

# Check status
./scripts/test-gke.sh status

# View logs
./scripts/test-gke.sh logs

# Clean up test job
./scripts/test-gke.sh cleanup
```

## Manual Deployment Steps

If you prefer to run the steps manually:

### Step 1: Configure Docker Authentication

```bash
gcloud auth configure-docker
```

### Step 2: Build Container Image

```bash
docker build -f Dockerfile.gke -t gcr.io/YOUR_PROJECT_ID/mls-scraper:latest .
```

### Step 3: Push to Container Registry

```bash
docker push gcr.io/YOUR_PROJECT_ID/mls-scraper:latest
```

### Step 4: Update Kubernetes Manifests

1. Update `k8s/cronjob.yaml`:
   - Replace `YOUR_PROJECT_ID` with your actual GCP project ID

2. Update `k8s/secret.yaml`:
   - Encode your API token: `echo -n "your-api-token" | base64`
   - Replace the empty value with the encoded token

### Step 5: Deploy to GKE

```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret.yaml
kubectl apply -f k8s/cronjob.yaml
```

## Wrapper Scripts

The project includes several wrapper scripts to simplify deployment:

### `deploy-gke-complete.sh`
- **Purpose**: Complete automated deployment using terraform/dev.tfvars
- **Features**: 
  - Reads configuration from existing terraform/dev.tfvars
  - Handles build, deploy, and test in one command
  - Interactive prompts for missing values
  - Comprehensive error checking and colored output
- **Usage**: `./scripts/deploy-gke-complete.sh [PROJECT_ID] [API_TOKEN]`

### `deploy-gke-env.sh`
- **Purpose**: Complete automated deployment using .env.dev file
- **Features**:
  - Reads configuration from .env.dev file
  - Handles build, deploy, and test in one command
  - Validates required environment variables
  - Comprehensive error checking and colored output
- **Usage**: `./scripts/deploy-gke-env.sh [.env.dev file path]`

### `build-and-push-gke.sh`
- **Purpose**: Build and push container image only
- **Usage**: `./scripts/build-and-push-gke.sh PROJECT_ID [TAG]`

### `deploy-to-gke.sh`
- **Purpose**: Deploy Kubernetes manifests only
- **Usage**: `./scripts/deploy-to-gke.sh PROJECT_ID API_TOKEN`

### `test-gke.sh`
- **Purpose**: Test and monitor GKE deployment
- **Usage**: `./scripts/test-gke.sh [trigger|status|logs|cleanup|monitor]`

## Configuration

### Environment Variables

The scraper uses the following configuration:

**From ConfigMap** (non-sensitive):
- `AGE_GROUP`: MLS age group (default: "U19")
- `DIVISION`: MLS division (default: "Premier")
- `MISSING_TABLE_API_BASE_URL`: API endpoint (default: "https://missing-table.com/api")
- `LOG_LEVEL`: Logging level (default: "INFO")
- `HEADLESS`: Run browser in headless mode (default: "true")
- `BROWSER_TIMEOUT`: Browser timeout in milliseconds (default: "30000")
- `MAX_RETRIES`: Maximum retry attempts (default: "3")
- `RETRY_DELAY`: Delay between retries in seconds (default: "5")

**From Secret** (sensitive):
- `MISSING_TABLE_API_TOKEN`: API authentication token

### Schedule

The CronJob runs daily at 6 AM UTC:
```yaml
schedule: "0 6 * * *"
timeZone: "UTC"
```

To modify the schedule, edit `k8s/cronjob.yaml` and reapply:
```bash
kubectl apply -f k8s/cronjob.yaml
```

## Monitoring and Troubleshooting

### Check CronJob Status

```bash
kubectl get cronjob -n match-scraper
kubectl describe cronjob mls-scraper-cronjob -n match-scraper
```

### View Job History

```bash
kubectl get jobs -n match-scraper --sort-by=.metadata.creationTimestamp
```

### Check Pod Logs

```bash
# Get recent jobs
kubectl get jobs -n match-scraper

# Get pods for a specific job
kubectl get pods -n match-scraper -l job-name=JOB_NAME

# View logs
kubectl logs POD_NAME -n match-scraper
```

### Manual Job Trigger

```bash
# Create a one-time job from the CronJob
kubectl create job --from=cronjob/mls-scraper-cronjob manual-run -n match-scraper

# Monitor the job
kubectl get pods -n match-scraper -l job-name=manual-run

# View logs
kubectl logs -l job-name=manual-run -n match-scraper
```

### Common Issues

1. **Image Pull Errors**:
   - Verify the image exists: `gcloud container images list --repository=gcr.io/YOUR_PROJECT_ID`
   - Check Docker authentication: `gcloud auth configure-docker`

2. **Permission Errors**:
   - Verify GKE cluster permissions
   - Check if the service account has necessary roles

3. **Playwright Issues**:
   - The GKE Dockerfile includes all necessary system dependencies
   - If issues persist, check the container logs for specific error messages

4. **API Authentication**:
   - Verify the API token is correctly encoded in the secret
   - Check the API endpoint URL in the ConfigMap

## Resource Management

### Resource Requests and Limits

The CronJob is configured with:
- **Requests**: 1Gi memory, 500m CPU
- **Limits**: 2Gi memory, 1000m CPU

These can be adjusted in `k8s/cronjob.yaml` based on your needs.

### GKE Autopilot

This deployment is optimized for GKE Autopilot, which automatically manages:
- Node provisioning and scaling
- Resource optimization
- Security updates

## Security

### Security Context

The container runs with:
- Non-root user (UID 1000)
- Read-only root filesystem disabled (required for Playwright)
- All capabilities dropped
- No privilege escalation

### Secrets Management

- API tokens are stored in Kubernetes secrets
- Secrets are base64 encoded (not encrypted)
- Consider using external secret management for production

## Cleanup

To remove the deployment:

```bash
kubectl delete -f k8s/cronjob.yaml
kubectl delete -f k8s/secret.yaml
kubectl delete -f k8s/configmap.yaml
kubectl delete -f k8s/namespace.yaml
```

To remove the container image:

```bash
gcloud container images delete gcr.io/YOUR_PROJECT_ID/mls-scraper:latest
```

## Observability

The scraper includes comprehensive observability using Grafana Cloud. See [OBSERVABILITY.md](OBSERVABILITY.md) for detailed setup instructions.

### Quick Setup

1. **Prerequisites**:
   - Grafana Cloud account (free tier available)
   - API tokens for metrics (OTLP) and logs (Loki)

2. **Configure Endpoints**:
   Edit `k8s/configmap.yaml`:
   ```yaml
   OTEL_EXPORTER_OTLP_ENDPOINT: "https://otlp-gateway-{zone}.grafana.net/otlp/v1/metrics"
   LOKI_ENDPOINT: "https://logs-{zone}.grafana.net/loki/api/v1/push"
   ```

3. **Configure Credentials**:
   Edit `k8s/secret.yaml` with base64-encoded tokens:
   ```bash
   # OTLP headers
   echo -n "instanceID:token" | base64
   echo -n "Authorization=Basic YOUR_BASE64" | base64

   # Loki token
   echo -n "your-loki-token" | base64
   ```

4. **Deploy**:
   ```bash
   kubectl apply -f k8s/configmap.yaml
   kubectl apply -f k8s/secret.yaml
   kubectl apply -f k8s/promtail-config.yaml
   kubectl apply -f k8s/cronjob.yaml
   ```

5. **Import Dashboards**:
   - Log into Grafana Cloud
   - Import `grafana/dashboards/scraper-overview.json`
   - Import `grafana/dashboards/scraper-errors.json`

### Available Metrics

- `games_scheduled_total` - Matches found
- `games_scored_total` - Matches with scores
- `api_calls_total` - API call counts and latency
- `scraping_errors_total` - Error tracking
- `application_execution_duration_seconds` - Execution time

### Viewing Logs

Logs are automatically forwarded to Grafana Loki:
```logql
{job="mls-match-scraper"}
{job="mls-match-scraper"} |= "ERROR"
```

## Migration from AWS Lambda

After successful GKE deployment and testing:

1. **Verify Functionality**:
   - Run multiple test jobs
   - Confirm data is being sent to the API
   - Monitor for any errors
   - Check metrics in Grafana Cloud

2. **Clean Up AWS Resources**:
   ```bash
   cd terraform
   terraform destroy -var-file=dev.tfvars -auto-approve
   ```

3. **Update Documentation**:
   - Update README.md to reflect GKE deployment
   - Archive AWS-specific documentation
