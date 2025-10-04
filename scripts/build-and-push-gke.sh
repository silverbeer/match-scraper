#!/bin/bash

# Build and push MLS Match Scraper container to GCP Container Registry
# Usage: ./scripts/build-and-push-gke.sh [PROJECT_ID] [TAG]

set -e

PROJECT_ID=${1:-""}
TAG=${2:-"latest"}

if [ -z "$PROJECT_ID" ]; then
    echo "Error: PROJECT_ID is required"
    echo "Usage: $0 <PROJECT_ID> [TAG]"
    echo "Example: $0 my-gcp-project v1.0.0"
    exit 1
fi

IMAGE_NAME="gcr.io/$PROJECT_ID/mls-scraper:$TAG"

echo "🔨 Building MLS Match Scraper container for GKE..."
echo "Project ID: $PROJECT_ID"
echo "Image: $IMAGE_NAME"

# Step 1: Configure Docker to use gcloud as a credential helper
echo "🔐 Configuring Docker authentication..."
gcloud auth configure-docker

# Step 2: Build the container image
echo "🏗️  Building container image..."
docker build -f Dockerfile.gke -t "$IMAGE_NAME" .

# Step 3: Push the image to GCP Container Registry
echo "📤 Pushing image to GCP Container Registry..."
docker push "$IMAGE_NAME"

echo ""
echo "✅ Container image built and pushed successfully!"
echo "Image: $IMAGE_NAME"
echo ""
echo "Next steps:"
echo "1. Deploy to GKE: ./scripts/deploy-to-gke.sh $PROJECT_ID"
echo "2. Or update the CronJob image: kubectl set image cronjob/mls-scraper-cronjob mls-scraper=$IMAGE_NAME -n match-scraper"
