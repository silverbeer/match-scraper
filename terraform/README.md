# GKE Deployment Guide

This directory contains Kubernetes manifests and deployment scripts for the MLS Match Scraper running on Google Kubernetes Engine (GKE).

## Table of Contents

- [Quick Start](#quick-start)
- [Manual Deployment](#manual-deployment)
- [Configuration](#configuration)
- [Testing and Monitoring](#testing-and-monitoring)
- [Troubleshooting](#troubleshooting)

## Quick Start

### Prerequisites

- GCP project with billing enabled
- GKE cluster (Autopilot recommended)
- Container Registry enabled
- `gcloud` CLI installed and authenticated
- `kubectl` configured to connect to your GKE cluster
- `docker` installed

### Automated Deployment

The easiest way to deploy the MLS Match Scraper to GKE is using the automated deployment script:

```bash
# From project root
./scripts/deploy-gke-complete.sh
```

This script will:
1. ✅ Check prerequisites (gcloud, kubectl, docker)
2. ✅ Load configuration from terraform/dev.tfvars
3. ✅ Build and push Docker image to GCP Container Registry
4. ✅ Deploy Kubernetes manifests (CronJob, ConfigMap, Secret)
5. ✅ Test the deployment with a manual job
6. ✅ Display deployment summary and management commands

### Alternative: Using .env.dev file

```bash
# Create environment file
cp env.dev.template .env.dev
# Edit .env.dev with your values

# Deploy using environment file
./scripts/deploy-gke-env.sh .env.dev
```

## Manual Deployment

If you prefer to deploy manually, follow these steps:

### Step 1: Configure Docker Authentication

```bash
gcloud auth configure-docker
```

### Step 2: Build and Push Container Image

```bash
# Get your project ID
PROJECT_ID=$(gcloud config get-value project)

# Build the image
docker build -f Dockerfile.gke -t gcr.io/$PROJECT_ID/mls-scraper:latest .

# Push to Container Registry
docker push gcr.io/$PROJECT_ID/mls-scraper:latest
```

### Step 3: Update Kubernetes Manifests

1. Update `k8s/cronjob.yaml`:
   - Replace `YOUR_PROJECT_ID` with your actual GCP project ID

2. Update `k8s/secret.yaml`:
   - Encode your API token: `echo -n "your-api-token" | base64`
   - Replace the empty value with the encoded token

### Step 4: Deploy to GKE

```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret.yaml
kubectl apply -f k8s/cronjob.yaml
```

### Step 5: Test the Deployment

```bash
# Create a test job
kubectl create job --from=cronjob/mls-scraper-cronjob test-run -n match-scraper

# Check job status
kubectl get jobs -n match-scraper

# View logs
kubectl logs -l job-name=test-run -n match-scraper

# Clean up test job
kubectl delete job test-run -n match-scraper
```

## Configuration

### Environment Variables

The scraper uses the following configuration:

**From ConfigMap** (non-sensitive):
- `AGE_GROUP`: MLS age group (default: "U14")
- `DIVISION`: MLS division (default: "Northeast")
- `MISSING_TABLE_API_BASE_URL`: API endpoint (default: "https://dev.missingtable.com")
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

## Testing and Monitoring

### Using the Test Script

```bash
# Trigger a test run
./scripts/test-gke.sh trigger

# Check status
./scripts/test-gke.sh status

# View logs
./scripts/test-gke.sh logs

# Monitor in real-time
./scripts/test-gke.sh monitor

# Clean up test jobs
./scripts/test-gke.sh cleanup
```

### Manual Testing Commands

```bash
# Check CronJob status
kubectl get cronjob -n match-scraper

# Check job history
kubectl get jobs -n match-scraper --sort-by=.metadata.creationTimestamp

# Check pod status
kubectl get pods -n match-scraper

# View logs from latest job
kubectl logs -l app=mls-scraper -n match-scraper --tail=100
```

## Troubleshooting

### Issue: "ImagePullBackOff" or "ErrImagePull"

**Cause**: Container image doesn't exist in GCP Container Registry.

**Solution**: Build and push the Docker image:
```bash
PROJECT_ID=$(gcloud config get-value project)
docker build -f Dockerfile.gke -t gcr.io/$PROJECT_ID/mls-scraper:latest .
docker push gcr.io/$PROJECT_ID/mls-scraper:latest
```

### Issue: "gcloud is not authenticated"

**Cause**: gcloud CLI not authenticated.

**Solution**:
```bash
gcloud auth login
gcloud auth configure-docker
```

### Issue: "kubectl context is not set"

**Cause**: kubectl not configured for GKE cluster.

**Solution**:
```bash
gcloud container clusters get-credentials CLUSTER_NAME --zone ZONE --project PROJECT_ID
```

### Issue: Job fails with "Playwright browser not found"

**Cause**: Playwright browsers not properly installed in container.

**Solution**: The GKE Dockerfile includes all necessary dependencies. If issues persist, check the container logs:
```bash
kubectl logs <pod-name> -n match-scraper
```

### Issue: API authentication fails

**Cause**: API token not properly configured.

**Solution**: Verify the secret is correctly set:
```bash
kubectl get secret mls-scraper-secrets -n match-scraper -o yaml
```

### View Resource Status

```bash
# Check all resources in namespace
kubectl get all -n match-scraper

# Get detailed information
kubectl describe cronjob mls-scraper-cronjob -n match-scraper
kubectl describe job <job-name> -n match-scraper
kubectl describe pod <pod-name> -n match-scraper
```

### Check Events

```bash
# View recent events
kubectl get events -n match-scraper --sort-by=.metadata.creationTimestamp
```

## Best Practices

1. **Use the automated deployment script**: Handles all prerequisites and configuration
2. **Test with manual jobs first**: Validate functionality before relying on scheduled runs
3. **Monitor resource usage**: Ensure your cluster can handle the workload
4. **Use descriptive job names**: Include timestamps for easy identification
5. **Clean up test jobs**: Remove completed jobs to avoid clutter
6. **Save important logs**: Archive logs for debugging and analysis
7. **Use GKE Autopilot**: Automatically manages node provisioning and scaling

## Additional Resources

- [GKE Documentation](https://cloud.google.com/kubernetes-engine/docs)
- [Kubernetes CronJob Documentation](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/)
- [GCP Container Registry Documentation](https://cloud.google.com/container-registry/docs)
- [Project GKE Deployment Guide](../GKE_DEPLOYMENT.md)
- [Testing and Monitoring Guide](../GKE_TESTING_GUIDE.md)
