# GitOps Dashboard Deployment Guide

This guide covers multiple methods for deploying Grafana dashboards using GitOps principles.

## Quick Start

The easiest GitOps method is **Terraform** (recommended) or **GitHub Actions** for automated deployments.

```bash
# Option 1: Terraform (Infrastructure as Code)
./scripts/deploy-grafana-dashboards.sh terraform

# Option 2: Manual API deployment
./scripts/deploy-grafana-dashboards.sh api

# Option 3: Grizzly (Grafana's GitOps tool)
./scripts/deploy-grafana-dashboards.sh grizzly
```

---

## Method 1: Terraform (Recommended)

**Best for**: Teams using Terraform, infrastructure as code workflows

### Prerequisites

- Terraform >= 1.0
- Grafana Cloud instance
- Service account token with `Admin` or `Editor` role

### Setup

1. **Create Grafana Service Account Token**:
   - Go to Grafana Cloud → Administration → Service Accounts
   - Create new service account: "terraform-dashboards"
   - Add role: `Editor` or `Admin`
   - Generate token and save it

2. **Configure Terraform**:
   ```bash
   cd terraform
   cp grafana.tfvars.example grafana.tfvars
   ```

3. **Edit `grafana.tfvars`**:
   ```hcl
   grafana_url       = "https://stack-1184667-hm-prod-us-east-2.grafana.net"
   grafana_api_token = "glsa_xxxxxxxxxxxxx"
   grafana_folder_title = "MLS Match Scraper"
   ```

4. **Deploy**:
   ```bash
   terraform init
   terraform plan -var-file=grafana.tfvars
   terraform apply -var-file=grafana.tfvars
   ```

### Update Dashboards

Simply edit the JSON files and run:
```bash
terraform apply -var-file=grafana.tfvars
```

### Advantages
- ✅ Full infrastructure as code
- ✅ State management and drift detection
- ✅ Rollback support
- ✅ Works with existing Terraform workflows

---

## Method 2: GitHub Actions (Automated GitOps)

**Best for**: Automatic deployment on git push

### Setup

1. **Add GitHub Secrets**:
   - `GRAFANA_URL`: Your Grafana instance URL
   - `GRAFANA_TOKEN`: Service account token

2. **The workflow is already configured** at `.github/workflows/deploy-grafana-dashboards.yml`

3. **Trigger Deployment**:
   - **Automatic**: Push changes to `grafana/dashboards/*.json` on main branch
   - **Manual**: Go to Actions → "Deploy Grafana Dashboards" → Run workflow

### Workflow Features
- Validates JSON before deployment
- Deploys both dashboards automatically
- Provides deployment summary
- Only runs when dashboard files change

### Advantages
- ✅ Fully automated
- ✅ No local setup required
- ✅ Deployment history in GitHub Actions
- ✅ Team collaboration friendly

---

## Method 3: Grafana Grizzly

**Best for**: Grafana-native GitOps workflows

### Prerequisites

Install Grizzly:
```bash
go install github.com/grafana/grizzly/cmd/grr@latest
```

### Setup

1. **Set environment variables**:
   ```bash
   export GRAFANA_URL="https://stack-1184667-hm-prod-us-east-2.grafana.net"
   export GRAFANA_TOKEN="glsa_xxxxxxxxxxxxx"
   ```

2. **Preview changes**:
   ```bash
   cd grafana/dashboards
   grr diff .
   ```

3. **Apply dashboards**:
   ```bash
   grr apply .
   ```

### Advantages
- ✅ Grafana's official GitOps tool
- ✅ Watch mode for live updates
- ✅ Diff preview before applying
- ✅ Supports all Grafana resources (dashboards, alerts, datasources)

---

## Method 4: Kubernetes Grafana Operator

**Best for**: Kubernetes-native deployments

### Prerequisites

- GKE cluster with Grafana Operator installed
- Grafana instance accessible from cluster

### Setup

1. **Install Grafana Operator**:
   ```bash
   kubectl apply -f https://raw.githubusercontent.com/grafana/grafana-operator/master/deploy/manifests/latest/crds.yaml
   kubectl apply -f https://raw.githubusercontent.com/grafana/grafana-operator/master/deploy/manifests/latest/deployment.yaml
   ```

2. **Deploy dashboards**:
   ```bash
   kubectl apply -f k8s/grafana-dashboard-overview.yaml
   kubectl apply -f k8s/grafana-dashboard-errors.yaml
   ```

3. **Update dashboards**:
   Edit the YAML files and reapply with `kubectl apply`.

### Advantages
- ✅ Kubernetes-native CRDs
- ✅ Declarative configuration
- ✅ Automatic reconciliation
- ✅ Works with ArgoCD/Flux

---

## Method 5: Direct API (Manual)

**Best for**: Quick testing, one-off deployments

### Setup

```bash
export GRAFANA_URL="https://stack-1184667-hm-prod-us-east-2.grafana.net"
export GRAFANA_TOKEN="glsa_xxxxxxxxxxxxx"

cd grafana/dashboards

# Deploy overview dashboard
curl -X POST "$GRAFANA_URL/api/dashboards/db" \
  -H "Authorization: Bearer $GRAFANA_TOKEN" \
  -H "Content-Type: application/json" \
  -d @scraper-overview.json

# Deploy errors dashboard
curl -X POST "$GRAFANA_URL/api/dashboards/db" \
  -H "Authorization: Bearer $GRAFANA_TOKEN" \
  -H "Content-Type: application/json" \
  -d @scraper-errors.json
```

Or use the helper script:
```bash
./scripts/deploy-grafana-dashboards.sh api
```

---

## Comparison Matrix

| Method | Setup Complexity | Automation | State Management | Rollback | Best For |
|--------|-----------------|------------|------------------|----------|----------|
| **Terraform** | Medium | Manual/CI | ✅ Yes | ✅ Easy | IaC teams |
| **GitHub Actions** | Low | ✅ Automatic | ❌ No | ✅ Via Git | CI/CD teams |
| **Grizzly** | Low | Manual/CI | ✅ Yes | ✅ Via Git | Grafana-focused |
| **K8s Operator** | High | ✅ Automatic | ✅ Yes | ✅ Easy | K8s-native |
| **API** | Very Low | Manual | ❌ No | ❌ Manual | Quick tests |

---

## Recommended Workflows

### For This Project

Since you're already using:
- ✅ GKE with Kubernetes manifests
- ✅ GitHub for version control
- ✅ Automated deployments

**Recommended approach**: **GitHub Actions** + **Terraform** (optional)

1. **Use GitHub Actions** for automatic dashboard deployments (already configured)
2. **Optionally add Terraform** if you want state management and drift detection

### Getting Started (Quickest)

```bash
# 1. Add GitHub secrets (do this once)
#    - GRAFANA_URL
#    - GRAFANA_TOKEN

# 2. Commit your dashboard changes
git add grafana/dashboards/*.json
git commit -m "feat: Update Grafana dashboards"
git push origin main

# 3. GitHub Actions deploys automatically! 🎉
```

---

## Token Permissions

Your Grafana service account token needs these permissions:

- **Dashboard**: Write (to create/update)
- **Folders**: Write (to create folders)
- **Data Sources**: Read (for validation)

**Minimum role**: `Editor`

---

## Troubleshooting

### "401 Unauthorized"
- Check token has correct permissions
- Verify token hasn't expired
- Ensure using service account token (not personal API key)

### "Dashboard not found after deployment"
- Check folder permissions
- Verify datasource UIDs match
- Look for dashboard UID conflicts

### "Version conflict"
- Set `overwrite: true` in Terraform
- Use `--force` flag with Grizzly
- Delete existing dashboard first

### "Invalid JSON"
- Validate with `jq`: `jq empty grafana/dashboards/scraper-overview.json`
- Check for trailing commas
- Verify all quotes are escaped properly

---

## Next Steps

1. Choose your deployment method (GitHub Actions recommended)
2. Set up authentication (Grafana service account token)
3. Test deployment with one dashboard
4. Automate for all dashboards
5. Set up monitoring for dashboard health

For questions, see the main [README](README.md) or Grafana documentation.
