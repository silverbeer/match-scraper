#!/bin/bash
set -e

# Set up EventBridge scheduled rule for MLS Scraper in LocalStack
# This creates a scheduled rule that triggers the Lambda function

LOCALSTACK_ENDPOINT="http://localhost:4566"
AWS_REGION="us-east-1"
FUNCTION_NAME="mls-scraper"
RULE_NAME="${FUNCTION_NAME}-schedule"

echo "⏰ Setting up EventBridge scheduled rule in LocalStack..."

# Set AWS credentials for LocalStack
export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test
export AWS_DEFAULT_REGION=${AWS_REGION}

# Step 1: Create EventBridge rule with schedule
echo ""
echo "📅 Creating scheduled rule..."
echo "   Schedule: Every day at 6 AM UTC (rate: 1 day)"

aws --endpoint-url=${LOCALSTACK_ENDPOINT} events put-rule \
    --name ${RULE_NAME} \
    --schedule-expression "cron(0 6 * * ? *)" \
    --state ENABLED \
    --description "Daily trigger for MLS match scraper at 6 AM UTC" \
    --region ${AWS_REGION}

# Step 2: Add Lambda function as target
echo ""
echo "🎯 Adding Lambda function as target..."

LAMBDA_ARN="arn:aws:lambda:${AWS_REGION}:000000000000:function:${FUNCTION_NAME}"

# Target input (event payload for Lambda)
TARGET_INPUT='{
  "age_group": "U14",
  "division": "Northeast",
  "start_offset": 1,
  "end_offset": 7,
  "enable_api_integration": true
}'

aws --endpoint-url=${LOCALSTACK_ENDPOINT} events put-targets \
    --rule ${RULE_NAME} \
    --targets "Id=1,Arn=${LAMBDA_ARN},Input='${TARGET_INPUT}'" \
    --region ${AWS_REGION}

# Step 3: Add Lambda permission for EventBridge to invoke
echo ""
echo "🔐 Granting EventBridge permission to invoke Lambda..."

aws --endpoint-url=${LOCALSTACK_ENDPOINT} lambda add-permission \
    --function-name ${FUNCTION_NAME} \
    --statement-id eventbridge-invoke \
    --action lambda:InvokeFunction \
    --principal events.amazonaws.com \
    --source-arn "arn:aws:events:${AWS_REGION}:000000000000:rule/${RULE_NAME}" \
    --region ${AWS_REGION} 2>/dev/null || echo "Permission already exists"

echo ""
echo "✅ EventBridge scheduled rule configured successfully!"
echo ""
echo "📝 Rule details:"
echo "   Name: ${RULE_NAME}"
echo "   Schedule: Every day at 6 AM UTC"
echo "   Target: ${FUNCTION_NAME} Lambda function"
echo "   Region: ${AWS_REGION}"
echo ""
echo "📋 View scheduled rules:"
echo "   aws --endpoint-url=${LOCALSTACK_ENDPOINT} events list-rules"
echo ""
echo "🧪 Test the rule manually:"
echo "   ./scripts/invoke_lambda_localstack.sh"
echo ""
echo "⚠️  Note: In LocalStack, scheduled rules may not trigger automatically."
echo "   Use the invoke script to test Lambda execution."
