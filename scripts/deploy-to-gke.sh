#!/bin/bash

# Deploy MLS Match Scraper to GKE
# Usage: ./scripts/deploy-to-gke.sh [PROJECT_ID] [API_TOKEN]

set -e

PROJECT_ID=${1:-""}
API_TOKEN=${2:-""}

if [ -z "$PROJECT_ID" ]; then
    echo "Error: PROJECT_ID is required"
    echo "Usage: $0 <PROJECT_ID> [API_TOKEN]"
    echo "Example: $0 my-gcp-project abc123xyz"
    exit 1
fi

if [ -z "$API_TOKEN" ]; then
    echo "Warning: API_TOKEN not provided. You'll need to update the secret manually."
    echo "To update later: kubectl create secret generic mls-scraper-secrets --from-literal=MISSING_TABLE_API_TOKEN='your-token' -n match-scraper --dry-run=client -o yaml | kubectl apply -f -"
fi

echo "🚀 Deploying MLS Match Scraper to GKE..."
echo "Project ID: $PROJECT_ID"

# Step 1: Update the CronJob with the correct project ID
echo "📝 Updating CronJob with project ID..."
sed -i.bak "s/YOUR_PROJECT_ID/$PROJECT_ID/g" k8s/cronjob.yaml

# Step 2: Update the secret with the API token if provided
if [ -n "$API_TOKEN" ]; then
    echo "🔐 Updating secret with API token..."
    ENCODED_TOKEN=$(echo -n "$API_TOKEN" | base64)
    sed -i.bak "s/MISSING_TABLE_API_TOKEN: \"\"/MISSING_TABLE_API_TOKEN: \"$ENCODED_TOKEN\"/g" k8s/secret.yaml
fi

# Step 3: Apply Kubernetes manifests
echo "📦 Applying Kubernetes manifests..."
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret.yaml
kubectl apply -f k8s/cronjob.yaml

# Step 4: Verify deployment
echo "✅ Verifying deployment..."
kubectl get cronjob -n match-scraper
kubectl get configmap -n match-scraper
kubectl get secret -n match-scraper

echo ""
echo "🎉 Deployment complete!"
echo ""
echo "Next steps:"
echo "1. Build and push the container image:"
echo "   docker build -f Dockerfile.gke -t gcr.io/$PROJECT_ID/mls-scraper:latest ."
echo "   docker push gcr.io/$PROJECT_ID/mls-scraper:latest"
echo ""
echo "2. Test the deployment:"
echo "   kubectl create job --from=cronjob/mls-scraper-cronjob test-run -n match-scraper"
echo "   kubectl get pods -n match-scraper -l job-name=test-run"
echo "   kubectl logs <pod-name> -n match-scraper"
echo ""
echo "3. Monitor the scheduled job:"
echo "   kubectl get cronjob -n match-scraper"
echo "   kubectl get jobs -n match-scraper"
