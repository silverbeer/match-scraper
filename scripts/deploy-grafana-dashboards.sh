#!/bin/bash
# Deploy Grafana Dashboards using various methods
# Usage: ./scripts/deploy-grafana-dashboards.sh [method]
# Methods: terraform, grizzly, api

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

METHOD="${1:-terraform}"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Helper functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check required environment variables
check_env() {
    local required_vars=("$@")
    for var in "${required_vars[@]}"; do
        if [[ -z "${!var:-}" ]]; then
            log_error "Required environment variable $var is not set"
            return 1
        fi
    done
}

# Method 1: Terraform
deploy_with_terraform() {
    log_info "Deploying dashboards with Terraform..."

    cd "$PROJECT_ROOT/terraform"

    # Check if grafana.tfvars exists
    if [[ ! -f "grafana.tfvars" ]]; then
        log_error "grafana.tfvars not found. Copy grafana.tfvars.example and fill in your values."
        return 1
    fi

    # Initialize Terraform
    log_info "Initializing Terraform..."
    terraform init

    # Plan
    log_info "Planning Terraform changes..."
    terraform plan -var-file=grafana.tfvars -target=grafana_dashboard.scraper_overview -target=grafana_dashboard.scraper_errors

    # Apply
    log_info "Applying Terraform changes..."
    terraform apply -var-file=grafana.tfvars -target=grafana_dashboard.scraper_overview -target=grafana_dashboard.scraper_errors -auto-approve

    log_info "✅ Dashboards deployed successfully with Terraform"
    terraform output
}

# Method 2: Grizzly
deploy_with_grizzly() {
    log_info "Deploying dashboards with Grizzly..."

    # Check if grr is installed
    if ! command -v grr &> /dev/null; then
        log_error "Grizzly (grr) is not installed. Install it with: go install github.com/grafana/grizzly/cmd/grr@latest"
        return 1
    fi

    # Check environment variables
    check_env GRAFANA_URL GRAFANA_TOKEN || return 1

    cd "$PROJECT_ROOT/grafana/dashboards"

    # Preview changes
    log_info "Previewing changes..."
    grr diff .

    # Apply
    log_info "Applying dashboards..."
    grr apply .

    log_info "✅ Dashboards deployed successfully with Grizzly"
}

# Method 3: Direct API
deploy_with_api() {
    log_info "Deploying dashboards with Grafana API..."

    # Check environment variables
    check_env GRAFANA_URL GRAFANA_TOKEN || return 1

    cd "$PROJECT_ROOT/grafana/dashboards"

    # Deploy Overview Dashboard
    log_info "Deploying scraper-overview.json..."
    curl -X POST "$GRAFANA_URL/api/dashboards/db" \
      -H "Authorization: Bearer $GRAFANA_TOKEN" \
      -H "Content-Type: application/json" \
      -d @scraper-overview.json

    echo ""

    # Deploy Errors Dashboard
    log_info "Deploying scraper-errors.json..."
    curl -X POST "$GRAFANA_URL/api/dashboards/db" \
      -H "Authorization: Bearer $GRAFANA_TOKEN" \
      -H "Content-Type: application/json" \
      -d @scraper-errors.json

    echo ""
    log_info "✅ Dashboards deployed successfully with API"
}

# Method 4: GitHub Actions (print instructions)
deploy_with_github_actions() {
    log_info "GitHub Actions GitOps Deployment"
    echo ""
    echo "To set up automated dashboard deployment with GitHub Actions:"
    echo ""
    echo "1. Add GitHub Secrets:"
    echo "   - GRAFANA_URL: Your Grafana instance URL"
    echo "   - GRAFANA_TOKEN: Service account token with dashboard write permissions"
    echo ""
    echo "2. Create workflow file: .github/workflows/deploy-grafana-dashboards.yml"
    echo ""
    echo "3. Dashboards will deploy automatically on:"
    echo "   - Push to main branch (changes to grafana/dashboards/*.json)"
    echo "   - Manual workflow dispatch"
    echo ""
    echo "See .github/workflows/deploy-grafana-dashboards.yml for the workflow template"
}

# Main
case "$METHOD" in
    terraform)
        deploy_with_terraform
        ;;
    grizzly)
        deploy_with_grizzly
        ;;
    api)
        deploy_with_api
        ;;
    github-actions)
        deploy_with_github_actions
        ;;
    *)
        log_error "Unknown method: $METHOD"
        echo "Usage: $0 [terraform|grizzly|api|github-actions]"
        echo ""
        echo "Methods:"
        echo "  terraform       - Deploy using Terraform (recommended for IaC)"
        echo "  grizzly         - Deploy using Grafana Grizzly (GitOps tool)"
        echo "  api             - Deploy using Grafana REST API"
        echo "  github-actions  - Show GitHub Actions setup instructions"
        exit 1
        ;;
esac
