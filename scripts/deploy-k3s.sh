#!/bin/bash
#
# Deploy match-scraper and RabbitMQ to local k3s cluster
#
# Usage:
#   ./scripts/deploy-k3s.sh                    # Full deployment
#   ./scripts/deploy-k3s.sh --skip-build       # Skip Docker build
#   ./scripts/deploy-k3s.sh --rabbitmq-only    # Deploy only RabbitMQ
#   ./scripts/deploy-k3s.sh --scraper-only     # Deploy only match-scraper
#

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
IMAGE_NAME="match-scraper"
IMAGE_TAG="latest"
IMAGE_FULL="${IMAGE_NAME}:${IMAGE_TAG}"
NAMESPACE="match-scraper"
DOCKERFILE="Dockerfile.gke"

# Parse arguments
SKIP_BUILD=false
RABBITMQ_ONLY=false
SCRAPER_ONLY=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-build)
            SKIP_BUILD=true
            shift
            ;;
        --rabbitmq-only)
            RABBITMQ_ONLY=true
            shift
            ;;
        --scraper-only)
            SCRAPER_ONLY=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--skip-build] [--rabbitmq-only] [--scraper-only]"
            exit 1
            ;;
    esac
done

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}K3s Deployment: match-scraper + RabbitMQ${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Step 1: Build Docker image (unless skipped or rabbitmq-only)
if [[ "$SKIP_BUILD" == false ]] && [[ "$RABBITMQ_ONLY" == false ]]; then
    echo -e "${YELLOW}📦 Building Docker image...${NC}"
    docker build -f "$DOCKERFILE" -t "$IMAGE_FULL" .

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ Docker image built successfully${NC}"
    else
        echo -e "${RED}❌ Docker build failed${NC}"
        exit 1
    fi
    echo ""

    # Step 2: Export and import to k3s
    echo -e "${YELLOW}📤 Exporting Docker image...${NC}"
    docker save "$IMAGE_FULL" -o /tmp/${IMAGE_NAME}.tar

    echo -e "${YELLOW}📥 Importing image into k3s...${NC}"
    sudo k3s ctr images import /tmp/${IMAGE_NAME}.tar

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ Image imported to k3s${NC}"
        rm /tmp/${IMAGE_NAME}.tar
    else
        echo -e "${RED}❌ Failed to import image to k3s${NC}"
        exit 1
    fi
    echo ""
else
    if [[ "$SKIP_BUILD" == true ]]; then
        echo -e "${YELLOW}⏭️  Skipping Docker build (using existing image)${NC}"
        echo ""
    fi
fi

# Step 3: Deploy RabbitMQ (unless scraper-only)
if [[ "$SCRAPER_ONLY" == false ]]; then
    echo -e "${YELLOW}🐰 Deploying RabbitMQ...${NC}"

    # Apply RabbitMQ manifests
    kubectl apply -f k3s/rabbitmq/namespace.yaml
    kubectl apply -f k3s/rabbitmq/secret.yaml
    kubectl apply -f k3s/rabbitmq/configmap.yaml
    kubectl apply -f k3s/rabbitmq/statefulset.yaml
    kubectl apply -f k3s/rabbitmq/service.yaml
    kubectl apply -f k3s/rabbitmq/service-nodeport.yaml

    echo -e "${GREEN}✅ RabbitMQ manifests applied${NC}"

    # Wait for RabbitMQ to be ready
    echo -e "${YELLOW}⏳ Waiting for RabbitMQ to be ready...${NC}"
    kubectl wait --for=condition=ready pod -l app=rabbitmq -n "$NAMESPACE" --timeout=300s

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ RabbitMQ is ready${NC}"
    else
        echo -e "${RED}❌ RabbitMQ failed to start (check logs with: kubectl logs -n $NAMESPACE -l app=rabbitmq)${NC}"
        exit 1
    fi
    echo ""
fi

# Step 4: Deploy match-scraper (unless rabbitmq-only)
if [[ "$RABBITMQ_ONLY" == false ]]; then
    echo -e "${YELLOW}⚽ Deploying match-scraper...${NC}"

    # Apply match-scraper manifests
    kubectl apply -f k3s/match-scraper/configmap.yaml
    kubectl apply -f k3s/match-scraper/secret.yaml
    kubectl apply -f k3s/match-scraper/cronjob.yaml

    echo -e "${GREEN}✅ Match-scraper manifests applied${NC}"
    echo ""
fi

# Step 5: Verify deployment
echo -e "${YELLOW}🔍 Verifying deployment...${NC}"
echo ""

if [[ "$SCRAPER_ONLY" == false ]]; then
    echo -e "${BLUE}RabbitMQ Status:${NC}"
    kubectl get pods -n "$NAMESPACE" -l app=rabbitmq
    echo ""

    echo -e "${BLUE}RabbitMQ Services:${NC}"
    kubectl get svc -n "$NAMESPACE" -l app=rabbitmq
    echo ""
fi

if [[ "$RABBITMQ_ONLY" == false ]]; then
    echo -e "${BLUE}CronJob Status:${NC}"
    kubectl get cronjob -n "$NAMESPACE"
    echo ""

    echo -e "${BLUE}Recent Jobs:${NC}"
    kubectl get jobs -n "$NAMESPACE" --sort-by=.metadata.creationTimestamp 2>/dev/null || echo "No jobs yet"
    echo ""
fi

# Step 6: Display helpful information
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}✅ Deployment Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

if [[ "$SCRAPER_ONLY" == false ]]; then
    echo -e "${BLUE}RabbitMQ Management UI:${NC}"
    echo "  Access at: http://localhost:30672"
    echo "  Username: admin"
    echo "  Password: admin123"
    echo ""
fi

if [[ "$RABBITMQ_ONLY" == false ]]; then
    echo -e "${BLUE}Useful Commands:${NC}"
    echo "  Trigger manual job:"
    echo "    kubectl create job --from=cronjob/match-scraper-cronjob test-run-\$(date +%s) -n $NAMESPACE"
    echo ""
    echo "  View CronJob logs:"
    echo "    kubectl logs -n $NAMESPACE -l app=match-scraper --tail=100 -f"
    echo ""
    echo "  Check CronJob status:"
    echo "    kubectl get cronjob -n $NAMESPACE"
    echo ""
    echo "  Delete a test job:"
    echo "    kubectl delete job <job-name> -n $NAMESPACE"
    echo ""
fi

echo -e "${BLUE}Next Steps:${NC}"
echo "  1. Ensure missing-table Celery workers are running and connected to RabbitMQ"
echo "  2. Trigger a manual job to test the pipeline"
echo "  3. Check RabbitMQ management UI to see queued messages"
echo "  4. Verify matches appear in Supabase"
echo ""
