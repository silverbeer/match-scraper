# Migration from AWS Lambda to GKE

This document outlines the complete migration plan from AWS Lambda to Google Kubernetes Engine (GKE) for the MLS Match Scraper.

## 🎯 **Migration Overview**

**Current State:** AWS Lambda + EventBridge + ECR + Terraform  
**Target State:** GKE CronJob + Container Registry + Kubernetes manifests

## 📋 **Migration Steps**

### **Phase 1: Preparation & Analysis**
1. **Audit Current Infrastructure**
   - Document current AWS resources
   - Identify what can be reused vs. what needs to be replaced
   - Plan data migration (if any)

2. **GKE Environment Setup**
   - Verify GKE cluster access
   - Set up Container Registry (or use existing)
   - Configure service accounts and permissions

### **Phase 2: Code & Container Changes**
3. **Simplify Dockerfile**
   - Remove Lambda-specific configurations
   - Optimize for standard Linux containers
   - Fix Playwright installation (much easier in GKE)

4. **Update Application Code**
   - Remove Lambda-specific handlers
   - Add Kubernetes health checks
   - Update logging for containerized environment

5. **Create Kubernetes Manifests**
   - CronJob for scheduling
   - ConfigMap for configuration
   - Secret for API tokens
   - Service account and RBAC

### **Phase 3: Deployment & Testing**
6. **Build and Push Container**
   - Build optimized Docker image
   - Push to Container Registry
   - Test locally with Docker

7. **Deploy to GKE**
   - Apply Kubernetes manifests
   - Test CronJob execution
   - Verify logging and monitoring

8. **Integration Testing**
   - Test scraping functionality
   - Verify API integration
   - Test scheduling and reliability

### **Phase 4: Cleanup & Optimization**
9. **AWS Cleanup**
   - Remove Lambda function
   - Clean up ECR repositories
   - Remove EventBridge rules
   - Clean up Terraform resources

10. **Monitoring & Alerting**
    - Set up GKE monitoring
    - Configure alerting for failures
    - Set up log aggregation

## 🔄 **Resource Mapping**

| AWS Resource | GKE Equivalent | Notes |
|--------------|----------------|-------|
| Lambda Function | CronJob + Pod | Scheduled execution |
| EventBridge | CronJob schedule | Kubernetes cron syntax |
| ECR | Container Registry | GCP Container Registry |
| CloudWatch Logs | GKE Logging | Stackdriver/Cloud Logging |
| IAM Roles | Service Accounts | Kubernetes RBAC |
| S3 State | GitOps | Store manifests in Git |

## 📁 **New File Structure**

```
├── k8s/                          # Kubernetes manifests
│   ├── cronjob.yaml             # Main CronJob
│   ├── configmap.yaml           # Configuration
│   ├── secret.yaml              # API tokens
│   ├── serviceaccount.yaml      # RBAC
│   └── rbac.yaml                # Permissions
├── docker/                      # Container files
│   ├── Dockerfile.gke           # GKE-optimized Dockerfile
│   └── .dockerignore            # Docker ignore file
├── scripts/                     # Deployment scripts
│   ├── deploy-gke.sh           # GKE deployment script
│   ├── build-and-push.sh       # Container build script
│   └── test-gke.sh             # GKE testing script
└── docs/                        # Documentation
    ├── GKE_DEPLOYMENT.md        # GKE deployment guide
    └── MIGRATION_TO_GKE.md      # This file
```

## 🚀 **Benefits of Migration**

### **Technical Benefits**
- ✅ **No Playwright Issues** - Full Linux environment
- ✅ **Easier Debugging** - Standard container logs
- ✅ **Better Resource Management** - Kubernetes handles scaling
- ✅ **Simpler Deployment** - Standard Docker + K8s
- ✅ **Cost Effective** - Only runs when needed

### **Operational Benefits**
- ✅ **Unified Infrastructure** - Everything in GCP
- ✅ **Better Monitoring** - Integrated with existing GKE monitoring
- ✅ **Easier Maintenance** - Standard Kubernetes operations
- ✅ **Better Security** - Integrated with existing GCP security

## ⚠️ **Risks & Mitigation**

| Risk | Impact | Mitigation |
|------|--------|------------|
| Data Loss | High | Backup all data before migration |
| Service Downtime | Medium | Run in parallel, then switch |
| Configuration Errors | Medium | Test thoroughly in dev environment |
| Performance Issues | Low | Monitor and optimize after migration |

## 📊 **Success Criteria**

- [ ] Scraper runs successfully in GKE
- [ ] Scheduling works correctly
- [ ] API integration functions
- [ ] Logging and monitoring work
- [ ] No data loss during migration
- [ ] Performance is acceptable
- [ ] AWS resources are cleaned up

## 🕐 **Timeline Estimate**

- **Phase 1:** 1-2 hours (Preparation)
- **Phase 2:** 2-3 hours (Code changes)
- **Phase 3:** 1-2 hours (Deployment)
- **Phase 4:** 1 hour (Cleanup)

**Total:** 5-8 hours

## 🎯 **Next Steps**

1. **Review this plan** - Make sure it covers everything
2. **Start with Phase 1** - Audit current infrastructure
3. **Execute step by step** - Don't rush the migration
4. **Test thoroughly** - Verify each step works
5. **Clean up AWS** - Only after GKE is working

---

**Ready to start?** Let's begin with Phase 1, Step 1: Auditing the current infrastructure.


