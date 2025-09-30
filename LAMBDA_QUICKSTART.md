# Lambda Deployment - Quick Start Guide

Get the MLS Match Scraper running in AWS Lambda with LocalStack in under 10 minutes.

## Prerequisites Check

Run the verification script to ensure you have everything needed:

```bash
./scripts/verify_lambda_setup.sh
```

This checks for:
- ✅ Docker (and Docker daemon running)
- ✅ AWS CLI
- ✅ jq (JSON processor)
- ✅ All deployment scripts
- ✅ Lambda handler code

If any checks fail, follow the instructions provided by the script.

## Quick Start (LocalStack)

### Step 1: Start Docker

Make sure Docker Desktop is running, or start the Docker daemon.

### Step 2: Start LocalStack

```bash
docker-compose -f docker-compose.localstack.yml up -d
```

Wait ~30 seconds for LocalStack to initialize, then verify:

```bash
curl http://localhost:4566/health
```

### Step 3: Deploy Lambda Function

```bash
./scripts/deploy_lambda_localstack.sh
```

This will:
- Build Docker image with Playwright (~5-10 minutes first time)
- Push to LocalStack ECR
- Create Lambda function

### Step 4: Test Lambda

```bash
./scripts/invoke_lambda_localstack.sh
```

The function will:
- Initialize Playwright browser
- Scrape MLS matches
- Return results

**Note**: First invocation may take 2-3 minutes due to Playwright initialization.

### Step 5: Set Up Scheduled Trigger

```bash
./scripts/setup_eventbridge_localstack.sh
```

This creates an EventBridge rule to trigger Lambda daily at 6 AM UTC.

## Viewing Results

### Check Lambda Response

The invoke script displays the Lambda response:

```json
{
  "statusCode": 200,
  "body": {
    "status": "success",
    "matches_found": 42,
    "age_group": "U14",
    "division": "Northeast",
    "date_range": "2025-09-29 to 2025-10-01"
  }
}
```

### View CloudWatch Logs

```bash
# Install awslocal for convenience (optional)
pip install awscli-local

# View logs
awslocal logs tail /aws/lambda/mls-scraper --follow

# Or use standard AWS CLI
aws --endpoint-url=http://localhost:4566 logs tail /aws/lambda/mls-scraper --follow
```

## Customizing the Deployment

### Change Age Group or Division

Edit the environment variables in `scripts/deploy_lambda_localstack.sh`:

```bash
AGE_GROUP=U16
DIVISION=Southwest
```

Then re-deploy:

```bash
./scripts/deploy_lambda_localstack.sh
```

### Or Override at Invocation Time

```bash
./scripts/invoke_lambda_localstack.sh '{
  "age_group": "U16",
  "division": "Southwest",
  "start_offset": 0,
  "end_offset": 7
}'
```

### Change Schedule

Edit the cron expression in `scripts/setup_eventbridge_localstack.sh`:

```bash
# Daily at 6 AM UTC
--schedule-expression "cron(0 6 * * ? *)"

# Every 12 hours
--schedule-expression "rate(12 hours)"

# Weekly on Mondays at 9 AM UTC
--schedule-expression "cron(0 9 ? * MON *)"
```

## Troubleshooting

### Docker Build Fails

```bash
# Clean Docker cache and rebuild
docker system prune -a
./scripts/deploy_lambda_localstack.sh
```

### Lambda Times Out

Increase timeout in `scripts/deploy_lambda_localstack.sh`:

```bash
--timeout 900  # 15 minutes (maximum)
```

### Out of Memory

Increase memory in `scripts/deploy_lambda_localstack.sh`:

```bash
--memory-size 3008  # Maximum available
```

### Playwright Errors

Check the CloudWatch logs for specific Playwright errors:

```bash
awslocal logs tail /aws/lambda/mls-scraper --follow
```

Common issues:
- Missing browser dependencies (check Dockerfile.lambda)
- Network connectivity issues
- Timeout during page load

### LocalStack Issues

```bash
# Restart LocalStack
docker-compose -f docker-compose.localstack.yml down
docker-compose -f docker-compose.localstack.yml up -d

# Check LocalStack logs
docker logs mls-scraper-localstack -f
```

## Cleaning Up

### Stop LocalStack

```bash
docker-compose -f docker-compose.localstack.yml down
```

### Remove All Lambda Resources

```bash
# Stop and remove containers
docker-compose -f docker-compose.localstack.yml down -v

# Remove LocalStack data
rm -rf localstack-data/
```

### Remove Docker Images

```bash
# Remove Lambda images
docker rmi mls-scraper:latest
docker rmi 000000000000.dkr.ecr.us-east-1.localhost.localstack.cloud:4566/mls-scraper:latest

# Clean up unused images
docker image prune -a
```

## Next Steps

Once working locally with LocalStack:

1. **Review the full deployment guide**: See [LAMBDA_DEPLOYMENT.md](LAMBDA_DEPLOYMENT.md) for AWS production deployment
2. **Configure the API**: Set up missing-table API integration with proper credentials
3. **Add monitoring**: Set up CloudWatch dashboards and alarms
4. **Optimize costs**: Adjust memory, timeout, and schedule based on usage
5. **Deploy to AWS**: Follow production deployment steps in the full guide

## Common Workflows

### Development Iteration

```bash
# 1. Make code changes to src/lambda_handler.py or scraper code

# 2. Re-deploy
./scripts/deploy_lambda_localstack.sh

# 3. Test
./scripts/invoke_lambda_localstack.sh

# 4. Check logs
awslocal logs tail /aws/lambda/mls-scraper
```

### Testing Different Configurations

```bash
# Test U14 Northeast
./scripts/invoke_lambda_localstack.sh '{
  "age_group": "U14",
  "division": "Northeast"
}'

# Test U16 Southwest
./scripts/invoke_lambda_localstack.sh '{
  "age_group": "U16",
  "division": "Southwest"
}'

# Test with API integration disabled
./scripts/invoke_lambda_localstack.sh '{
  "enable_api_integration": false
}'
```

### Monitoring Execution Time

```bash
# Run test and time it
time ./scripts/invoke_lambda_localstack.sh

# Or check CloudWatch metrics
awslocal cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Duration \
  --dimensions Name=FunctionName,Value=mls-scraper \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 3600 \
  --statistics Average,Maximum
```

## Support

For issues or questions:
- Check [LAMBDA_DEPLOYMENT.md](LAMBDA_DEPLOYMENT.md) for detailed documentation
- Review [TESTING_README.md](TESTING_README.md) for testing guidance
- Open an issue on GitHub
