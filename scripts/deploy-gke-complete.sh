#!/bin/bash

# Complete GKE Deployment Script for MLS Match Scraper
# This script handles build, deploy, and test in one go
# Usage: ./scripts/deploy-gke-complete.sh [PROJECT_ID] [API_TOKEN]

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

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to check prerequisites
check_prerequisites() {
    print_status "Checking prerequisites..."

    local missing_commands=()

    if ! command_exists gcloud; then
        missing_commands+=("gcloud")
    fi

    if ! command_exists kubectl; then
        missing_commands+=("kubectl")
    fi

    if ! command_exists docker; then
        missing_commands+=("docker")
    fi

    if [ ${#missing_commands[@]} -ne 0 ]; then
        print_error "Missing required commands: ${missing_commands[*]}"
        print_error "Please install the missing tools and try again."
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

# Function to get project ID
get_project_id() {
    local project_id=""

    # Try to get from gcloud config
    if command_exists gcloud; then
        project_id=$(gcloud config get-value project 2>/dev/null || echo "")
    fi

    # If not set, prompt user
    if [ -z "$project_id" ]; then
        echo -n "Enter your GCP Project ID: "
        read -r project_id
    fi

    if [ -z "$project_id" ]; then
        print_error "Project ID is required"
        exit 1
    fi

    echo "$project_id"
}

# Function to get API token
get_api_token() {
    local api_token=""

    # Try to get from terraform dev.tfvars or environment
    if [ -f "terraform/dev.tfvars" ]; then
        # Check if there's a TF_VAR_missing_table_api_token in environment
        api_token="${TF_VAR_missing_table_api_token:-}"
    fi

    # If not found, prompt user
    if [ -z "$api_token" ]; then
        echo -n "Enter your Missing Table API Token: "
        read -r -s api_token
        echo
    fi

    if [ -z "$api_token" ]; then
        print_warning "API token not provided. You'll need to update the secret manually later."
    fi

    echo "$api_token"
}

# Function to load configuration from terraform/dev.tfvars
load_config() {
    print_status "Loading configuration from terraform/dev.tfvars..."

    if [ ! -f "terraform/dev.tfvars" ]; then
        print_error "terraform/dev.tfvars not found. Please ensure the file exists."
        exit 1
    fi

    # Extract values from dev.tfvars
    AGE_GROUP=$(grep '^age_group' terraform/dev.tfvars | cut -d'"' -f2)
    DIVISION=$(grep '^division' terraform/dev.tfvars | cut -d'"' -f2)
    API_BASE_URL=$(grep '^missing_table_api_base_url' terraform/dev.tfvars | cut -d'"' -f2)
    LOG_LEVEL=$(grep '^log_level' terraform/dev.tfvars | cut -d'"' -f2)

    # Set defaults if not found
    AGE_GROUP=${AGE_GROUP:-"U14"}
    DIVISION=${DIVISION:-"Northeast"}
    API_BASE_URL=${API_BASE_URL:-"https://dev.missingtable.com"}
    LOG_LEVEL=${LOG_LEVEL:-"INFO"}

    print_success "Configuration loaded:"
    echo "  Age Group: $AGE_GROUP"
    echo "  Division: $DIVISION"
    echo "  API Base URL: $API_BASE_URL"
    echo "  Log Level: $LOG_LEVEL"
}

# Function to update ConfigMap with loaded values
update_configmap() {
    print_status "Updating ConfigMap with configuration values..."

    # Create a temporary ConfigMap file
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
  AGE_GROUP: "$AGE_GROUP"
  DIVISION: "$DIVISION"
  MISSING_TABLE_API_BASE_URL: "$API_BASE_URL"

  # Logging Configuration
  LOG_LEVEL: "$LOG_LEVEL"

  # Browser Configuration
  HEADLESS: "true"
  BROWSER_TIMEOUT: "30000"

  # Scraping Configuration
  MAX_RETRIES: "3"
  RETRY_DELAY: "5"
EOF

    print_success "ConfigMap updated with terraform/dev.tfvars values"
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

    # Update secret with API token if provided
    if [ -n "$api_token" ]; then
        print_status "Updating secret with API token..."
        local encoded_token
        encoded_token=$(echo -n "$api_token" | base64)
        sed -i.bak "s/MISSING_TABLE_API_TOKEN: \"\"/MISSING_TABLE_API_TOKEN: \"$encoded_token\"/g" k8s/secret.yaml
    fi

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
    echo ""
    echo "🧹 Cleanup (when ready):"
    echo "  kubectl delete -f k8s/ -n match-scraper"
    echo "  gcloud container images delete gcr.io/$project_id/mls-scraper:latest"
}

# Main execution
main() {
    echo "🚀 MLS Match Scraper - Complete GKE Deployment"
    echo "=============================================="
    echo ""

    # Parse command line arguments
    local project_id="$1"
    local api_token="$2"
    local skip_test="${3:-false}"

    # Check prerequisites
    check_prerequisites

    # Get project ID if not provided
    if [ -z "$project_id" ]; then
        project_id=$(get_project_id)
    fi

    # Get API token if not provided
    if [ -z "$api_token" ]; then
        api_token=$(get_api_token)
    fi

    print_status "Starting deployment with:"
    echo "  Project ID: $project_id"
    echo "  API Token: ${api_token:+[PROVIDED]}${api_token:-[NOT PROVIDED]}"
    echo ""

    # Load configuration from terraform/dev.tfvars
    load_config

    # Update ConfigMap with loaded values
    update_configmap

    # Build and push container
    build_and_push "$project_id"

    # Deploy to GKE
    deploy_to_gke "$project_id" "$api_token"

    # Test deployment (unless skipped)
    if [ "$skip_test" != "true" ]; then
        test_deployment
    else
        print_warning "Skipping test deployment"
    fi

    # Show final status
    show_final_status "$project_id"
}

# Run main function with all arguments
main "$@"
