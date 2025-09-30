#!/bin/bash
set -e

# Invoke MLS Scraper Lambda in LocalStack
# This script invokes the Lambda function with test parameters

LOCALSTACK_ENDPOINT="http://localhost:4566"
AWS_REGION="us-east-1"
FUNCTION_NAME="mls-scraper"

echo "🚀 Invoking Lambda function in LocalStack..."

# Set AWS credentials for LocalStack
export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test
export AWS_DEFAULT_REGION=${AWS_REGION}

# Default test event
EVENT_PAYLOAD='{
  "age_group": "U14",
  "division": "Northeast",
  "start_offset": 1,
  "end_offset": 1,
  "enable_api_integration": false
}'

# Allow custom event via argument
if [ $# -gt 0 ]; then
    EVENT_PAYLOAD="$1"
fi

echo ""
echo "📦 Event payload:"
echo "${EVENT_PAYLOAD}" | jq .

echo ""
echo "⏳ Invoking Lambda function..."
echo "   (This may take several minutes for web scraping to complete)"

# Invoke Lambda function
aws --endpoint-url=${LOCALSTACK_ENDPOINT} lambda invoke \
    --function-name ${FUNCTION_NAME} \
    --payload "${EVENT_PAYLOAD}" \
    --region ${AWS_REGION} \
    response.json

echo ""
echo "✅ Lambda invocation completed!"
echo ""
echo "📄 Response:"
cat response.json | jq .

echo ""
echo "📋 CloudWatch Logs:"
echo "   View logs with: awslocal logs tail /aws/lambda/${FUNCTION_NAME} --follow"

# Clean up response file
rm -f response.json
