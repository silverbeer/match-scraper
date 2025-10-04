# Terraform Deployment Strategy for Multiple Environments

This document explains how to manage dev and prod Lambda deployments.

## Current Approach: Separate tfvars Files

**Status**: ✅ Already Implemented

Our current setup uses:
- Single set of `.tf` files
- Separate variable files: `dev.tfvars` and `prod.tfvars`
- Separate S3 state keys for each environment
- Environment name in resource names to avoid conflicts

### How It Works

```bash
# Deploy to dev
terraform init \
  -backend-config="key=mls-scraper/dev/terraform.tfstate"
terraform apply -var-file=dev.tfvars

# Deploy to prod
terraform init -reconfigure \
  -backend-config="key=mls-scraper/prod/terraform.tfstate"
terraform apply -var-file=prod.tfvars
```

### Resource Naming

Resources are automatically namespaced by environment:

| Resource | Dev | Prod |
|----------|-----|------|
| Lambda Function | `mls-scraper-dev` | `mls-scraper-prod` |
| ECR Repository | `mls-scraper-dev` | `mls-scraper-prod` |
| IAM Role | `mls-scraper-dev-role` | `mls-scraper-prod-role` |
| Log Group | `/aws/lambda/mls-scraper-dev` | `/aws/lambda/mls-scraper-prod` |
| EventBridge Rule | `mls-scraper-dev-schedule` | `mls-scraper-prod-schedule` |

### Advantages ✅

- **Simple**: No workspace commands to remember
- **Clear separation**: Different state files per environment
- **Easy to understand**: Explicit tfvars file selection
- **GitHub Actions friendly**: Easy to parameterize
- **No conflicts**: Resources have different names

### GitHub Actions Integration

Our workflow already supports this:

```yaml
# Automatic environment selection
- Push to main → deploys to dev
- Create tag v* → deploys to prod
- Manual dispatch → choose environment
```

The workflow handles state backend configuration automatically.

## Alternative: Terraform Workspaces

**Status**: 📝 Alternative approach (not currently used)

If you prefer workspaces:

```bash
# Create workspaces
terraform workspace new dev
terraform workspace new prod

# Switch and deploy
terraform workspace select dev
terraform apply -var-file=dev.tfvars

terraform workspace select prod
terraform apply -var-file=prod.tfvars
```

### Workspaces vs Our Approach

| Aspect | Current (tfvars) | Workspaces |
|--------|------------------|------------|
| State separation | ✅ Different keys | ✅ Different workspaces |
| Resource naming | ✅ Explicit in tfvars | ⚠️ Need `terraform.workspace` |
| CI/CD | ✅ Simple | ⚠️ Extra workspace commands |
| Learning curve | ✅ Easy | ⚠️ Need to understand workspaces |
| Visibility | ✅ Clear from tfvars | ⚠️ Need to check `workspace show` |

**Recommendation**: Stick with the current tfvars approach.

## Alternative: Separate Directories

**Status**: 📝 For very different environments (not recommended here)

```
terraform/
├── dev/
│   ├── main.tf
│   ├── variables.tf
│   └── terraform.tfvars
└── prod/
    ├── main.tf
    ├── variables.tf
    └── terraform.tfvars
```

### When to Use

Only if dev and prod have significantly different infrastructure (e.g., different VPC configurations, different services enabled).

**For our use case**: ❌ Overkill. Dev and prod are identical except for configuration values.

## Best Practices for Our Setup

### 1. Environment-Specific Configuration

Keep environment differences in tfvars files:

**`dev.tfvars`**:
```hcl
environment               = "dev"
lambda_log_retention_days = 7      # Short retention
schedule_enabled          = false  # Manual testing only
end_offset                = 1      # Small date range
```

**`prod.tfvars`**:
```hcl
environment               = "prod"
lambda_log_retention_days = 30     # Longer retention
schedule_enabled          = true   # Automatic daily runs
end_offset                = 7      # Full week
```

### 2. State Backend Organization

```
S3 Bucket: mls-scraper-terraform-state
├── mls-scraper/dev/terraform.tfstate
└── mls-scraper/prod/terraform.tfstate
```

Each environment has its own state file to prevent interference.

### 3. Prevent Accidental Cross-Environment Changes

Our GitHub Actions workflow prevents mistakes:

```yaml
# Prod requires tag creation (deliberate action)
tags:
  - 'v*'

# Dev auto-deploys from main (safe for testing)
branches:
  - main
```

### 4. Resource Tagging

All resources are tagged with environment:

```hcl
tags = {
  Project     = "mls-scraper"
  Environment = var.environment  # "dev" or "prod"
  ManagedBy   = "terraform"
}
```

This helps with:
- Cost tracking (filter by Environment tag)
- Resource identification
- AWS Config compliance

## Common Operations

### Deploy to Dev

```bash
cd terraform

# First time
terraform init \
  -backend-config="bucket=mls-scraper-terraform-state" \
  -backend-config="key=mls-scraper/dev/terraform.tfstate" \
  -backend-config="region=us-east-1"

# Apply
export TF_VAR_missing_table_api_token=your-token
terraform apply -var-file=dev.tfvars
```

### Deploy to Prod

```bash
cd terraform

# Reconfigure backend for prod
terraform init -reconfigure \
  -backend-config="bucket=mls-scraper-terraform-state" \
  -backend-config="key=mls-scraper/prod/terraform.tfstate" \
  -backend-config="region=us-east-1"

# Apply
export TF_VAR_missing_table_api_token=your-token
terraform apply -var-file=prod.tfvars
```

### Via GitHub Actions (Recommended)

```bash
# Deploy to dev
git push origin main

# Deploy to prod
git tag v1.0.0
git push origin v1.0.0

# Or use manual dispatch
# Go to Actions → Deploy Lambda to AWS → Run workflow → Select environment
```

## Cost Optimization

### Dev Environment
- Shorter log retention (7 days)
- Schedule disabled by default
- Smaller date ranges
- Can destroy when not needed:
  ```bash
  terraform destroy -var-file=dev.tfvars
  ```

### Prod Environment
- Longer log retention (30 days)
- Schedule enabled
- Full date ranges
- Alarms enabled (via `count` in main.tf)
- Always running

## Migration Path

If you later need workspaces or separate directories:

1. **Export current state**
   ```bash
   terraform state pull > dev-state-backup.json
   ```

2. **Create new structure**

3. **Import resources**
   ```bash
   terraform import aws_lambda_function.scraper mls-scraper-dev
   ```

But for now, the current approach is optimal for your use case.

## Summary

**Current Strategy**: ✅ **Separate tfvars + Separate S3 state keys**

This is the best approach for your needs because:
- ✅ Simple and clear
- ✅ Works great with GitHub Actions
- ✅ No resource naming conflicts
- ✅ Easy to maintain
- ✅ Industry standard for multi-environment deployments

No changes needed!
