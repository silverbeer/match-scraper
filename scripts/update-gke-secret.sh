#!/bin/bash
set -e

# Update GKE Secret from .env.dev
# This script updates the MISSING_TABLE_API_TOKEN secret in GKE from your .env.dev file
# Usage: ./scripts/update-gke-secret.sh [.env.dev file path]

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
NAMESPACE="match-scraper"
ENV_FILE="${1:-.env.dev}"

echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║${NC}  ${GREEN}Update GKE Secret from .env.dev${NC}                          ${BLUE}║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Check if .env.dev exists
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${RED}Error: Environment file not found: $ENV_FILE${NC}"
    exit 1
fi

# Load .env.dev
echo -e "${BLUE}📄 Loading environment from: $ENV_FILE${NC}"
set -a
source "$ENV_FILE"
set +a

# Check if token is set
if [ -z "$MISSING_TABLE_API_TOKEN" ]; then
    echo -e "${RED}Error: MISSING_TABLE_API_TOKEN not found in $ENV_FILE${NC}"
    exit 1
fi

# Check if RabbitMQ URL is set and replace localhost with GKE service name
if [ -z "$RABBITMQ_URL" ]; then
    echo -e "${YELLOW}Warning: RABBITMQ_URL not found in $ENV_FILE${NC}"
    echo -e "${YELLOW}Using default GKE RabbitMQ URL${NC}"
    RABBITMQ_URL="amqp://admin:admin123@messaging-rabbitmq.missing-table-dev.svc.cluster.local:5672//"
elif [[ "$RABBITMQ_URL" == *"localhost"* ]]; then
    echo -e "${YELLOW}Detected localhost in RABBITMQ_URL, replacing with GKE service name${NC}"
    RABBITMQ_URL="amqp://admin:admin123@messaging-rabbitmq.missing-table-dev.svc.cluster.local:5672//"
fi

echo -e "${GREEN}✓ Configuration loaded from environment file${NC}"
echo ""

# Check if kubectl is available
if ! command -v kubectl &> /dev/null; then
    echo -e "${RED}Error: kubectl not found. Please install kubectl first.${NC}"
    exit 1
fi

# Check if cluster is accessible
if ! kubectl cluster-info &> /dev/null; then
    echo -e "${RED}Error: Cannot connect to Kubernetes cluster.${NC}"
    echo -e "${YELLOW}Hint: Make sure you're authenticated to GKE:${NC}"
    echo "  gcloud container clusters get-credentials CLUSTER_NAME --region REGION"
    exit 1
fi

echo -e "${BLUE}🔐 Updating Kubernetes secret...${NC}"

# Delete existing secret if it exists
kubectl delete secret mls-scraper-secrets -n $NAMESPACE --ignore-not-found=true

# Create new secret
kubectl create secret generic mls-scraper-secrets \
  -n $NAMESPACE \
  --from-literal=MISSING_TABLE_API_TOKEN="$MISSING_TABLE_API_TOKEN" \
  --from-literal=RABBITMQ_URL="$RABBITMQ_URL" \
  --from-literal=OTEL_EXPORTER_OTLP_HEADERS="$OTEL_EXPORTER_OTLP_HEADERS" \
  --from-literal=GRAFANA_CLOUD_API_TOKEN="$GRAFANA_TOKEN"

echo -e "${GREEN}✓ Secret updated successfully${NC}"
echo ""

# Verify the secret
echo -e "${BLUE}📋 Verifying secret...${NC}"
kubectl get secret mls-scraper-secrets -n $NAMESPACE -o yaml | grep -A 1 "data:"

echo ""
echo -e "${GREEN}✓ Secret verification complete${NC}"
echo ""

echo -e "${YELLOW}Note: Existing pods will continue to use the old secret.${NC}"
echo -e "${YELLOW}To use the new secret, restart pods or trigger a new job:${NC}"
echo ""
echo "  # Restart the CronJob by deleting and recreating it:"
echo "  kubectl delete cronjob mls-scraper-cronjob -n $NAMESPACE"
echo "  kubectl apply -f k8s/cronjob.yaml"
echo ""
echo "  # Or trigger a new manual job:"
echo "  ./scripts/trigger-gke-job.sh --from 2025-10-09 --to 2025-10-31"
echo ""
