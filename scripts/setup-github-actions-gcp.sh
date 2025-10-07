#!/bin/bash

# Setup GitHub Actions for GKE Deployment
# This script automates the GCP configuration for GitHub Actions Workload Identity Federation
#
# Usage: ./scripts/setup-github-actions-gcp.sh
#
# Prerequisites:
# - gcloud CLI installed and authenticated
# - Project with billing enabled
# - Permissions to create service accounts and configure IAM

set -e

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

success() {
    echo -e "${GREEN}✓${NC} $1"
}

warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

error() {
    echo -e "${RED}✗${NC} $1"
}

prompt() {
    echo -e "${YELLOW}?${NC} $1"
}

# Print banner
echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║  GitHub Actions GCP Setup for GKE Deployment              ║"
echo "║  Setting up Workload Identity Federation                  ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# Step 1: Get or confirm GCP Project ID
info "Step 1/9: GCP Project Configuration"
CURRENT_PROJECT=$(gcloud config get-value project 2>/dev/null || echo "")

if [ -n "$CURRENT_PROJECT" ]; then
    prompt "Current GCP project: $CURRENT_PROJECT"
    read -p "Use this project? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        PROJECT_ID="$CURRENT_PROJECT"
    else
        read -p "Enter GCP Project ID: " PROJECT_ID
        gcloud config set project "$PROJECT_ID"
    fi
else
    read -p "Enter GCP Project ID: " PROJECT_ID
    gcloud config set project "$PROJECT_ID"
fi

# Get project number
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)")
success "Using project: $PROJECT_ID (Project #: $PROJECT_NUMBER)"
echo ""

# Step 2: Get GitHub repository
info "Step 2/9: GitHub Repository Configuration"
read -p "Enter GitHub repository (e.g., username/repo-name): " GITHUB_REPO

if [[ ! "$GITHUB_REPO" =~ ^[a-zA-Z0-9_-]+/[a-zA-Z0-9_-]+$ ]]; then
    error "Invalid repository format. Expected: username/repo-name"
    exit 1
fi

success "GitHub repository: $GITHUB_REPO"
echo ""

# Step 3: Enable required APIs
info "Step 3/9: Enabling Required GCP APIs"
info "This may take a few minutes..."

APIS=(
    "iamcredentials.googleapis.com"
    "container.googleapis.com"
    "cloudresourcemanager.googleapis.com"
    "iam.googleapis.com"
    "storage.googleapis.com"
)

for api in "${APIS[@]}"; do
    info "Enabling $api..."
    gcloud services enable "$api" --project="$PROJECT_ID" 2>/dev/null || true
done

success "All required APIs enabled"
echo ""

# Step 4: Create Service Account
info "Step 4/9: Creating Service Account"
SERVICE_ACCOUNT_NAME="github-actions-gke"
SA_EMAIL="${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

# Check if service account already exists
if gcloud iam service-accounts describe "$SA_EMAIL" --project="$PROJECT_ID" &>/dev/null; then
    warning "Service account $SA_EMAIL already exists"
    read -p "Continue with existing service account? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        error "Aborted by user"
        exit 1
    fi
else
    gcloud iam service-accounts create "$SERVICE_ACCOUNT_NAME" \
        --display-name="GitHub Actions GKE Deployer" \
        --description="Service account for GitHub Actions to deploy to GKE" \
        --project="$PROJECT_ID"
    success "Service account created: $SA_EMAIL"
fi
echo ""

# Step 5: Grant IAM Permissions
info "Step 5/9: Granting IAM Permissions to Service Account"

ROLES=(
    "roles/container.developer"
    "roles/storage.admin"
    "roles/artifactregistry.writer"
)

for role in "${ROLES[@]}"; do
    info "Granting $role..."
    gcloud projects add-iam-policy-binding "$PROJECT_ID" \
        --member="serviceAccount:${SA_EMAIL}" \
        --role="$role" \
        --condition=None \
        --quiet 2>/dev/null || true
done

success "IAM permissions granted"
echo ""

# Step 6: Create Workload Identity Pool
info "Step 6/9: Creating Workload Identity Pool"
POOL_NAME="github-actions-pool"

# Check if pool exists
if gcloud iam workload-identity-pools describe "$POOL_NAME" \
    --project="$PROJECT_ID" \
    --location="global" &>/dev/null; then
    warning "Workload Identity Pool already exists"
else
    gcloud iam workload-identity-pools create "$POOL_NAME" \
        --project="$PROJECT_ID" \
        --location="global" \
        --display-name="GitHub Actions Pool" \
        --description="Workload Identity Pool for GitHub Actions"
    success "Workload Identity Pool created"
fi

WORKLOAD_IDENTITY_POOL_ID=$(gcloud iam workload-identity-pools describe "$POOL_NAME" \
    --project="$PROJECT_ID" \
    --location="global" \
    --format="value(name)")

success "Pool ID: $WORKLOAD_IDENTITY_POOL_ID"
echo ""

# Step 7: Create Workload Identity Provider
info "Step 7/9: Creating Workload Identity Provider"
PROVIDER_NAME="github-actions-provider"

# Check if provider exists
if gcloud iam workload-identity-pools providers describe "$PROVIDER_NAME" \
    --project="$PROJECT_ID" \
    --location="global" \
    --workload-identity-pool="$POOL_NAME" &>/dev/null; then
    warning "Workload Identity Provider already exists"
else
    gcloud iam workload-identity-pools providers create-oidc "$PROVIDER_NAME" \
        --project="$PROJECT_ID" \
        --location="global" \
        --workload-identity-pool="$POOL_NAME" \
        --display-name="GitHub Actions Provider" \
        --description="OIDC provider for GitHub Actions" \
        --issuer-uri="https://token.actions.githubusercontent.com" \
        --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.actor=assertion.actor" \
        --attribute-condition="assertion.repository=='${GITHUB_REPO}'"
    success "Workload Identity Provider created"
fi

WORKLOAD_IDENTITY_PROVIDER=$(gcloud iam workload-identity-pools providers describe "$PROVIDER_NAME" \
    --project="$PROJECT_ID" \
    --location="global" \
    --workload-identity-pool="$POOL_NAME" \
    --format="value(name)")

success "Provider: $WORKLOAD_IDENTITY_PROVIDER"
echo ""

# Step 8: Allow GitHub Repository to Impersonate Service Account
info "Step 8/9: Configuring Repository Access"
info "Allowing repository $GITHUB_REPO to impersonate service account..."

gcloud iam service-accounts add-iam-policy-binding "$SA_EMAIL" \
    --project="$PROJECT_ID" \
    --role="roles/iam.workloadIdentityUser" \
    --member="principalSet://iam.googleapis.com/${WORKLOAD_IDENTITY_POOL_ID}/attribute.repository/${GITHUB_REPO}"

success "Repository authorized to use service account"
echo ""

# Step 9: Generate Summary
info "Step 9/9: Generating Configuration Summary"
echo ""

# Create output file
OUTPUT_FILE="github-actions-secrets.txt"
cat > "$OUTPUT_FILE" << EOF
╔════════════════════════════════════════════════════════════╗
║  GitHub Actions Secrets Configuration                     ║
╚════════════════════════════════════════════════════════════╝

Add these secrets to your GitHub repository:
Settings → Secrets and variables → Actions → New repository secret

──────────────────────────────────────────────────────────────
Secret Name: GCP_PROJECT_ID
Value:
$PROJECT_ID

──────────────────────────────────────────────────────────────
Secret Name: GCP_SERVICE_ACCOUNT
Value:
$SA_EMAIL

──────────────────────────────────────────────────────────────
Secret Name: GCP_WORKLOAD_IDENTITY_PROVIDER
Value:
$WORKLOAD_IDENTITY_PROVIDER

──────────────────────────────────────────────────────────────

GitHub Repository: $GITHUB_REPO
Setup Date: $(date)

Next Steps:
1. Add the above secrets to your GitHub repository
2. Ensure your GKE cluster exists and is accessible
3. Create Kubernetes secrets in your cluster (if not already done)
4. Trigger the workflow manually or push to main branch

Verification Commands:
  # Verify service account
  gcloud iam service-accounts describe $SA_EMAIL

  # List service account permissions
  gcloud projects get-iam-policy $PROJECT_ID \\
    --flatten="bindings[].members" \\
    --format="table(bindings.role)" \\
    --filter="bindings.members:$SA_EMAIL"

  # Test authentication (from GitHub Actions)
  # This will be done automatically by the workflow

EOF

success "Setup complete! 🎉"
echo ""

# Display secrets
echo "════════════════════════════════════════════════════════════"
echo "  GitHub Secrets Configuration"
echo "════════════════════════════════════════════════════════════"
echo ""
echo "Add these secrets to your GitHub repository:"
echo "Repository → Settings → Secrets and variables → Actions"
echo ""
echo "Secret 1: GCP_PROJECT_ID"
echo "─────────────────────────────────────────────────────────"
echo "$PROJECT_ID"
echo ""
echo "Secret 2: GCP_SERVICE_ACCOUNT"
echo "─────────────────────────────────────────────────────────"
echo "$SA_EMAIL"
echo ""
echo "Secret 3: GCP_WORKLOAD_IDENTITY_PROVIDER"
echo "─────────────────────────────────────────────────────────"
echo "$WORKLOAD_IDENTITY_PROVIDER"
echo ""
echo "════════════════════════════════════════════════════════════"
echo ""

success "Configuration saved to: $OUTPUT_FILE"
echo ""

# Offer to copy to clipboard (if available)
if command -v pbcopy &> /dev/null; then
    read -p "Copy secrets to clipboard? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        cat "$OUTPUT_FILE" | pbcopy
        success "Secrets copied to clipboard!"
    fi
elif command -v xclip &> /dev/null; then
    read -p "Copy secrets to clipboard? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        cat "$OUTPUT_FILE" | xclip -selection clipboard
        success "Secrets copied to clipboard!"
    fi
fi

# Additional setup reminders
echo ""
info "Additional Setup Required:"
echo "  1. Add the above secrets to GitHub repository"
echo "  2. Update workflow environment variables if needed:"
echo "     - GKE_CLUSTER (current: missing-table-cluster)"
echo "     - GKE_ZONE (current: us-central1-a)"
echo "     - NAMESPACE (current: match-scraper)"
echo ""
echo "  3. Create Kubernetes secrets in GKE cluster:"
echo "     kubectl create secret generic mls-scraper-secrets \\"
echo "       -n match-scraper \\"
echo "       --from-literal=MISSING_TABLE_API_TOKEN='...' \\"
echo "       --from-literal=OTEL_EXPORTER_OTLP_HEADERS='...' \\"
echo "       --from-literal=LOKI_USER_ID='...' \\"
echo "       --from-literal=LOKI_API_KEY='...'"
echo ""

warning "Keep the $OUTPUT_FILE file secure and delete it after adding secrets to GitHub!"
echo ""

exit 0
