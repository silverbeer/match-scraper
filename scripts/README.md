# Scripts Directory

This directory contains utility scripts for the MLS Match Scraper project.

## Deployment Scripts

### GitHub Actions GCP Setup
**`setup-github-actions-gcp.sh`** - Automated setup for GitHub Actions deployment to GKE

Sets up Workload Identity Federation, service accounts, and IAM permissions.

```bash
./scripts/setup-github-actions-gcp.sh
```

**Prerequisites:**
- `gcloud` CLI installed and authenticated
- GCP project with billing enabled
- Permissions to create service accounts and configure IAM

**What it does:**
1. Enables required GCP APIs
2. Creates service account `github-actions-gke@PROJECT_ID.iam.gserviceaccount.com`
3. Grants necessary IAM roles
4. Creates Workload Identity Pool and Provider
5. Configures repository access
6. Generates GitHub Secrets configuration

**Output:**
- Creates `github-actions-secrets.txt` with values to add to GitHub
- Displays all secrets in terminal for easy copying

---

### GKE Deployment Scripts

**`build-and-push-gke.sh`** - Build and push Docker image to GCR

```bash
./scripts/build-and-push-gke.sh PROJECT_ID [TAG]
```

**`deploy-to-gke.sh`** - Deploy to GKE cluster

```bash
./scripts/deploy-to-gke.sh PROJECT_ID [API_TOKEN]
```

**`deploy-gke-complete.sh`** - Complete end-to-end deployment

```bash
./scripts/deploy-gke-complete.sh
```

**`deploy-gke-env.sh`** - Deploy with environment configuration

```bash
./scripts/deploy-gke-env.sh
```

---

## Testing Scripts

**`test-gke.sh`** - Test GKE deployment

```bash
./scripts/test-gke.sh
```

**`trigger-scrape.sh`** - Manually trigger a scrape job

```bash
./scripts/trigger-scrape.sh
```

---

## Utility Scripts

**`check_coverage.sh`** - Check code coverage

```bash
./scripts/check_coverage.sh
```

**`fix-database.sh`** - Fix database issues

```bash
./scripts/fix-database.sh
```

---

## Quick Reference

| Task | Command |
|------|---------|
| Set up GitHub Actions | `./scripts/setup-github-actions-gcp.sh` |
| Build & push image | `./scripts/build-and-push-gke.sh PROJECT_ID` |
| Deploy to GKE | `./scripts/deploy-to-gke.sh PROJECT_ID` |
| Test deployment | `./scripts/test-gke.sh` |
| Manual scrape | `./scripts/trigger-scrape.sh` |

---

See individual scripts for detailed usage and options.
