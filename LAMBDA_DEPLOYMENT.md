# AWS Lambda Deployment Guide

This guide covers deploying the MLS Match Scraper as an AWS Lambda function with EventBridge scheduling, including local testing with LocalStack.

## Overview

The Lambda deployment runs the scraper on a scheduled basis (e.g., daily) to automatically collect match data and post it to the missing-table API.

### Architecture

- **Lambda Function**: Containerized Python function using Playwright for web scraping
- **EventBridge**: Scheduled trigger (cron expression)
- **ECR**: Container image repository
- **CloudWatch**: Logs and metrics
- **Missing Table API**: Target for scraped match data

## Prerequisites

- Docker installed and running
- AWS CLI installed (`brew install awscli`)
- `jq` for JSON parsing (`brew install jq`)
- LocalStack (for local testing)

## Local Development with LocalStack

### 1. Start LocalStack

```bash
# Start LocalStack services
docker-compose -f docker-compose.localstack.yml up -d

# Verify LocalStack is running
curl http://localhost:4566/health
```

### 2. Deploy Lambda to LocalStack

```bash
# Build image, push to LocalStack ECR, and create Lambda function
./scripts/deploy_lambda_localstack.sh
```

This script will:
- Build the Docker image with Playwright and dependencies
- Create ECR repository in LocalStack
- Push image to LocalStack ECR
- Create IAM role for Lambda
- Create Lambda function with environment variables

### 3. Test Lambda Invocation

```bash
# Invoke with default test event
./scripts/invoke_lambda_localstack.sh

# Or provide custom event
./scripts/invoke_lambda_localstack.sh '{
  "age_group": "U16",
  "division": "Southwest",
  "start_offset": 0,
  "end_offset": 7,
  "enable_api_integration": false
}'
```

### 4. Set Up EventBridge Schedule

```bash
# Create scheduled rule to trigger Lambda daily
./scripts/setup_eventbridge_localstack.sh
```

This creates a rule that triggers the Lambda function daily at 6 AM UTC.

### 5. View Logs

```bash
# Install awslocal wrapper (optional but convenient)
pip install awscli-local

# View Lambda logs
awslocal logs tail /aws/lambda/mls-scraper --follow

# Or with standard AWS CLI
aws --endpoint-url=http://localhost:4566 logs tail /aws/lambda/mls-scraper --follow
```

## AWS Production Deployment

### 1. Build and Push to ECR

```bash
# Authenticate to ECR
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin <account-id>.dkr.ecr.us-east-1.amazonaws.com

# Create ECR repository
aws ecr create-repository --repository-name mls-scraper --region us-east-1

# Build and tag image
docker build -f Dockerfile.lambda -t mls-scraper:latest .
docker tag mls-scraper:latest <account-id>.dkr.ecr.us-east-1.amazonaws.com/mls-scraper:latest

# Push to ECR
docker push <account-id>.dkr.ecr.us-east-1.amazonaws.com/mls-scraper:latest
```

### 2. Create IAM Role

```bash
# Create role with trust policy
aws iam create-role \
  --role-name mls-scraper-lambda-role \
  --assume-role-policy-document file://lambda-trust-policy.json

# Attach execution policy
aws iam attach-role-policy \
  --role-name mls-scraper-lambda-role \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
```

Trust policy (`lambda-trust-policy.json`):
```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"Service": "lambda.amazonaws.com"},
    "Action": "sts:AssumeRole"
  }]
}
```

### 3. Create Lambda Function

```bash
aws lambda create-function \
  --function-name mls-scraper \
  --package-type Image \
  --code ImageUri=<account-id>.dkr.ecr.us-east-1.amazonaws.com/mls-scraper:latest \
  --role arn:aws:iam::<account-id>:role/mls-scraper-lambda-role \
  --timeout 900 \
  --memory-size 2048 \
  --environment Variables="{
    AGE_GROUP=U14,
    DIVISION=Northeast,
    START_OFFSET=1,
    END_OFFSET=1,
    MISSING_TABLE_API_BASE_URL=https://api.missing-table.com,
    MISSING_TABLE_API_TOKEN=<your-api-token>,
    LOG_LEVEL=INFO,
    ENABLE_TEAM_CACHE=true,
    CACHE_REFRESH_ON_MISS=true,
    CACHE_PRELOAD_TIMEOUT=30
  }" \
  --region us-east-1
```

### 4. Create EventBridge Schedule

```bash
# Create rule
aws events put-rule \
  --name mls-scraper-daily \
  --schedule-expression "cron(0 6 * * ? *)" \
  --state ENABLED \
  --description "Daily trigger for MLS match scraper at 6 AM UTC"

# Add Lambda as target
aws events put-targets \
  --rule mls-scraper-daily \
  --targets "Id=1,Arn=arn:aws:lambda:us-east-1:<account-id>:function:mls-scraper,Input='{\"age_group\":\"U14\",\"division\":\"Northeast\",\"start_offset\":1,\"end_offset\":7,\"enable_api_integration\":true}'"

# Grant EventBridge permission to invoke Lambda
aws lambda add-permission \
  --function-name mls-scraper \
  --statement-id eventbridge-invoke \
  --action lambda:InvokeFunction \
  --principal events.amazonaws.com \
  --source-arn arn:aws:events:us-east-1:<account-id>:rule/mls-scraper-daily
```

## Environment Variables

Configure these in the Lambda function:

| Variable | Description | Default |
|----------|-------------|---------|
| `AGE_GROUP` | Age group to scrape (U13-U19) | `U14` |
| `DIVISION` | Division to scrape | `Northeast` |
| `START_OFFSET` | Days backward from today | `1` |
| `END_OFFSET` | Days forward from today | `1` |
| `MISSING_TABLE_API_BASE_URL` | API base URL | Required |
| `MISSING_TABLE_API_TOKEN` | API authentication token | Required |
| `LOG_LEVEL` | Logging level (DEBUG, INFO, ERROR) | `INFO` |
| `ENABLE_TEAM_CACHE` | Enable team caching | `true` |
| `CACHE_REFRESH_ON_MISS` | Refresh cache on miss | `true` |
| `CACHE_PRELOAD_TIMEOUT` | Cache preload timeout (seconds) | `30` |

## Lambda Event Schema

The Lambda function accepts events with the following structure:

```json
{
  "age_group": "U14",           // Optional: override env var
  "division": "Northeast",       // Optional: override env var
  "start_offset": 1,            // Optional: override env var
  "end_offset": 7,              // Optional: override env var
  "enable_api_integration": true // Optional: enable/disable API posting
}
```

## CloudWatch Metrics

The Lambda function emits custom CloudWatch metrics:

- `MatchesFound`: Total matches scraped
- `ScheduledMatches`: Matches with scheduled status
- `CompletedMatches`: Matches with completed status
- `ScoredMatches`: Matches with scores
- `ScraperErrors`: Number of scraper errors
- `LambdaErrors`: Number of Lambda errors

Dimensions:
- `AgeGroup`: Age group being scraped
- `Division`: Division being scraped

## Troubleshooting

### Lambda Timeout

If the function times out (900 seconds max):
- Reduce date range (`start_offset` and `end_offset`)
- Increase memory (faster execution)
- Split into multiple smaller Lambda invocations

### Playwright Issues

If Playwright fails in Lambda:
- Ensure Chromium dependencies are installed in Dockerfile
- Check Lambda memory allocation (minimum 2048 MB recommended)
- Review CloudWatch logs for Playwright errors

### API Connection Issues

For missing-table API connection errors:
- Verify `MISSING_TABLE_API_BASE_URL` is correct
- Check `MISSING_TABLE_API_TOKEN` is valid
- Ensure Lambda has internet access (VPC configuration if applicable)
- Test with `enable_api_integration: false` to isolate scraping issues

### LocalStack Limitations

LocalStack limitations to be aware of:
- EventBridge scheduled rules may not trigger automatically
- Use manual invocation for testing: `./scripts/invoke_lambda_localstack.sh`
- Lambda execution may be slower than AWS
- Some AWS features may not be fully supported

## Cost Optimization

To optimize Lambda costs:

1. **Adjust Memory**: Test with different memory sizes (1024-3008 MB)
2. **Reduce Frequency**: Run less frequently (e.g., weekly vs. daily)
3. **Filter Data**: Scrape only specific divisions or age groups
4. **Cold Start**: Accept cold starts vs. keeping warm with provisioned concurrency
5. **Timeout**: Set timeout just above typical execution time

## Monitoring

### CloudWatch Dashboard

Create a CloudWatch dashboard to monitor:
- Invocation count
- Error rate
- Duration
- Custom metrics (matches found, etc.)
- Log insights queries

### Alarms

Set up CloudWatch alarms for:
- Lambda errors > 0
- Duration > 800 seconds (near timeout)
- MatchesFound = 0 (possible scraping failure)

### Log Insights Queries

Useful queries:

```
# Find all scraping errors
fields @timestamp, @message
| filter @message like /ERROR/
| sort @timestamp desc

# Count matches found per invocation
fields @timestamp
| stats sum(matches_found) as total_matches by bin(5m)

# Average execution duration
fields @duration
| stats avg(@duration) as avg_duration
```

## Next Steps

1. Test locally with LocalStack
2. Deploy to AWS development account
3. Monitor and optimize
4. Set up alarms and dashboards
5. Deploy to production

## Related Documentation

- [Main README](README.md)
- [CLI Documentation](CLI_README.md)
- [Testing Guide](TESTING_README.md)
