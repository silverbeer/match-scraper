#!/bin/bash

# Complete GKE Deployment Script using .env.dev file
# This script reads configuration from .env.dev and handles build, deploy, and test
# Usage: ./scripts/deploy-gke-env.sh [.env.dev file path]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to load environment variables from .env file
load_env_file() {
    local env_file="${1:-.env.dev}"

    if [ ! -f "$env_file" ]; then
        print_error "Environment file not found: $env_file"
        print_error "Please create the file or use the template: cp env.dev.template .env.dev"
        exit 1
    fi

    print_status "Loading environment from: $env_file"

    # Export variables from .env file
    set -a  # automatically export all variables
    source "$env_file"
    set +a  # stop automatically exporting

    # Validate required variables
    local missing_vars=()

    if [ -z "$GCP_PROJECT_ID" ]; then
        missing_vars+=("GCP_PROJECT_ID")
    fi

    if [ -z "$MISSING_TABLE_API_TOKEN" ]; then
        missing_vars+=("MISSING_TABLE_API_TOKEN")
    fi

    if [ ${#missing_vars[@]} -ne 0 ]; then
        print_error "Missing required environment variables: ${missing_vars[*]}"
        print_error "Please check your $env_file file"
        exit 1
    fi

    print_success "Environment loaded successfully!"
    echo "  Project ID: $GCP_PROJECT_ID"
    echo "  API Base URL: ${MISSING_TABLE_API_BASE_URL:-https://dev.missingtable.com}"
    echo "  Age Group: ${AGE_GROUP:-U14}"
    echo "  Division: ${DIVISION:-Northeast}"
}

# Function to check prerequisites
check_prerequisites() {
    print_status "Checking prerequisites..."

    local missing_commands=()

    if ! command -v gcloud >/dev/null 2>&1; then
        missing_commands+=("gcloud")
    fi

    if ! command -v kubectl >/dev/null 2>&1; then
        missing_commands+=("kubectl")
    fi

    if ! command -v docker >/dev/null 2>&1; then
        missing_commands+=("docker")
    fi

    if [ ${#missing_commands[@]} -ne 0 ]; then
        print_error "Missing required commands: ${missing_commands[*]}"
        exit 1
    fi

    # Check if gcloud is authenticated
    if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q .; then
        print_error "gcloud is not authenticated. Please run 'gcloud auth login' first."
        exit 1
    fi

    # Check if kubectl context is set
    if ! kubectl config current-context >/dev/null 2>&1; then
        print_error "kubectl context is not set. Please configure kubectl for your GKE cluster."
        exit 1
    fi

    print_success "All prerequisites met!"
}

# Function to update ConfigMap with environment values
update_configmap() {
    print_status "Updating ConfigMap with environment values..."

    # Set defaults
    local age_group="${AGE_GROUP:-U14}"
    local division="${DIVISION:-Northeast}"
    local api_base_url="${MISSING_TABLE_API_BASE_URL:-https://dev.missingtable.com}"
    local log_level="${LOG_LEVEL:-INFO}"
    local headless="${HEADLESS:-true}"
    local browser_timeout="${BROWSER_TIMEOUT:-30000}"
    local max_retries="${MAX_RETRIES:-3}"
    local retry_delay="${RETRY_DELAY:-5}"

    # Create ConfigMap
    cat > k8s/configmap.yaml << EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: mls-scraper-config
  namespace: match-scraper
  labels:
    app: mls-scraper
data:
  # MLS Configuration
  AGE_GROUP: "$age_group"
  DIVISION: "$division"
  MISSING_TABLE_API_BASE_URL: "$api_base_url"

  # Logging Configuration
  LOG_LEVEL: "$log_level"

  # Browser Configuration
  HEADLESS: "$headless"
  BROWSER_TIMEOUT: "$browser_timeout"

  # Scraping Configuration
  MAX_RETRIES: "$max_retries"
  RETRY_DELAY: "$retry_delay"
EOF

    print_success "ConfigMap updated with environment values"
}

# Function to build and push container
build_and_push() {
    local project_id="$1"
    local tag="${2:-latest}"

    print_status "Building and pushing container image..."

    local image_name="gcr.io/$project_id/mls-scraper:$tag"

    # Configure Docker authentication
    print_status "Configuring Docker authentication..."
    gcloud auth configure-docker --quiet

    # Build the image
    print_status "Building container image: $image_name"
    docker build -f Dockerfile.gke -t "$image_name" .

    # Push the image
    print_status "Pushing image to GCP Container Registry..."
    docker push "$image_name"

    print_success "Container image built and pushed: $image_name"
}

# Function to deploy to GKE
deploy_to_gke() {
    local project_id="$1"
    local api_token="$2"

    print_status "Deploying to GKE..."

    # Update CronJob with project ID
    print_status "Updating CronJob with project ID..."
    sed -i.bak "s/YOUR_PROJECT_ID/$project_id/g" k8s/cronjob.yaml

    # Update secret with API token
    print_status "Updating secret with API token..."
    local encoded_token
    encoded_token=$(echo -n "$api_token" | base64)
    sed -i.bak "s/MISSING_TABLE_API_TOKEN: \"\"/MISSING_TABLE_API_TOKEN: \"$encoded_token\"/g" k8s/secret.yaml

    # Apply Kubernetes manifests
    print_status "Applying Kubernetes manifests..."
    kubectl apply -f k8s/namespace.yaml
    kubectl apply -f k8s/configmap.yaml
    kubectl apply -f k8s/secret.yaml
    kubectl apply -f k8s/cronjob.yaml

    # Verify deployment
    print_status "Verifying deployment..."
    kubectl get cronjob -n match-scraper
    kubectl get configmap -n match-scraper
    kubectl get secret -n match-scraper

    print_success "Deployment completed successfully!"
}

# Function to test the deployment
test_deployment() {
    print_status "Testing the deployment..."

    local job_name="test-run-$(date +%s)"

    # Create test job
    print_status "Creating test job: $job_name"
    kubectl create job --from=cronjob/mls-scraper-cronjob "$job_name" -n match-scraper

    # Wait for pod to be created
    print_status "Waiting for pod to be created..."
    local pod_name=""
    local attempts=0
    local max_attempts=30

    while [ -z "$pod_name" ] && [ $attempts -lt $max_attempts ]; do
        pod_name=$(kubectl get pods -n match-scraper -l job-name="$job_name" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
        if [ -z "$pod_name" ]; then
            sleep 2
            attempts=$((attempts + 1))
        fi
    done

    if [ -z "$pod_name" ]; then
        print_error "Failed to create pod for test job"
        return 1
    fi

    print_success "Test pod created: $pod_name"

    # Wait for pod to complete
    print_status "Waiting for job to complete..."
    kubectl wait --for=condition=complete job/"$job_name" -n match-scraper --timeout=600s

    # Get job status
    local job_status
    job_status=$(kubectl get job "$job_name" -n match-scraper -o jsonpath='{.status.conditions[0].type}' 2>/dev/null || echo "Unknown")

    if [ "$job_status" = "Complete" ]; then
        print_success "Test job completed successfully!"
    else
        print_warning "Test job status: $job_status"
    fi

    # Show logs
    print_status "Fetching job logs..."
    kubectl logs "$pod_name" -n match-scraper --tail=50

    # Clean up test job
    print_status "Cleaning up test job..."
    kubectl delete job "$job_name" -n match-scraper --ignore-not-found=true

    print_success "Test completed!"
}

# Function to show final status
show_final_status() {
    local project_id="$1"

    print_success "🎉 MLS Match Scraper successfully deployed to GKE!"
    echo ""
    echo "📋 Deployment Summary:"
    echo "  Project ID: $project_id"
    echo "  Namespace: match-scraper"
    echo "  Schedule: Daily at 6 AM UTC"
    echo "  Image: gcr.io/$project_id/mls-scraper:latest"
    echo ""
    echo "🔧 Management Commands:"
    echo "  View CronJob: kubectl get cronjob -n match-scraper"
    echo "  View Jobs: kubectl get jobs -n match-scraper"
    echo "  Manual Run: kubectl create job --from=cronjob/mls-scraper-cronjob manual-run -n match-scraper"
    echo "  View Logs: kubectl logs -l job-name=manual-run -n match-scraper"
    echo ""
    echo "📊 Monitoring:"
    echo "  Use: ./scripts/test-gke.sh status"
    echo "  Or: ./scripts/test-gke.sh monitor"
}

# Main execution
main() {
    echo "🚀 MLS Match Scraper - Complete GKE Deployment (Environment File)"
    echo "==============================================================="
    echo ""

    local env_file="${1:-.env.dev}"

    # Check prerequisites
    check_prerequisites

    # Load environment file
    load_env_file "$env_file"

    print_status "Starting deployment with:"
    echo "  Project ID: $GCP_PROJECT_ID"
    echo "  API Token: [PROVIDED]"
    echo ""

    # Update ConfigMap with environment values
    update_configmap

    # Build and push container
    build_and_push "$GCP_PROJECT_ID"

    # Deploy to GKE
    deploy_to_gke "$GCP_PROJECT_ID" "$MISSING_TABLE_API_TOKEN"

    # Test deployment
    test_deployment

    # Show final status
    show_final_status "$GCP_PROJECT_ID"
}

# Run main function with all arguments
main "$@"
