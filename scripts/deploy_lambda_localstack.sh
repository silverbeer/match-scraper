#!/bin/bash
set -e

# Deploy MLS Scraper Lambda to LocalStack
# This script builds the Docker image, pushes to LocalStack ECR, and creates Lambda function

LOCALSTACK_ENDPOINT="http://localhost:4566"
AWS_REGION="us-east-1"
FUNCTION_NAME="mls-scraper"
IMAGE_TAG="latest"
ECR_REPO_NAME="mls-scraper"

echo "🚀 Deploying MLS Scraper to LocalStack Lambda..."

# Check if LocalStack is running
if ! curl -s "${LOCALSTACK_ENDPOINT}/health" > /dev/null; then
    echo "❌ LocalStack is not running. Start it with: docker-compose -f docker-compose.localstack.yml up -d"
    exit 1
fi

echo "✅ LocalStack is running"

# Set AWS credentials for LocalStack
export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test
export AWS_DEFAULT_REGION=${AWS_REGION}

# Step 1: Build Docker image
echo ""
echo "📦 Building Lambda Docker image..."
docker build -f Dockerfile.lambda -t ${ECR_REPO_NAME}:${IMAGE_TAG} .

# Step 2: Create ECR repository in LocalStack (if it doesn't exist)
echo ""
echo "🗂️  Creating ECR repository in LocalStack..."
aws --endpoint-url=${LOCALSTACK_ENDPOINT} ecr create-repository \
    --repository-name ${ECR_REPO_NAME} \
    --region ${AWS_REGION} 2>/dev/null || echo "Repository already exists"

# Step 3: Tag image for LocalStack ECR
echo ""
echo "🏷️  Tagging image for LocalStack ECR..."
ECR_URI="000000000000.dkr.ecr.${AWS_REGION}.localhost.localstack.cloud:4566/${ECR_REPO_NAME}:${IMAGE_TAG}"
docker tag ${ECR_REPO_NAME}:${IMAGE_TAG} ${ECR_URI}

# Step 4: Push image to LocalStack ECR
echo ""
echo "⬆️  Pushing image to LocalStack ECR..."
docker push ${ECR_URI}

# Step 5: Create IAM role for Lambda (if it doesn't exist)
echo ""
echo "🔐 Creating IAM role for Lambda..."
ROLE_NAME="${FUNCTION_NAME}-role"
ROLE_ARN="arn:aws:iam::000000000000:role/${ROLE_NAME}"

aws --endpoint-url=${LOCALSTACK_ENDPOINT} iam create-role \
    --role-name ${ROLE_NAME} \
    --assume-role-policy-document '{
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "lambda.amazonaws.com"},
            "Action": "sts:AssumeRole"
        }]
    }' 2>/dev/null || echo "Role already exists"

# Attach basic Lambda execution policy
aws --endpoint-url=${LOCALSTACK_ENDPOINT} iam attach-role-policy \
    --role-name ${ROLE_NAME} \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole \
    2>/dev/null || true

# Step 6: Delete existing Lambda function (if it exists)
echo ""
echo "🗑️  Removing existing Lambda function..."
aws --endpoint-url=${LOCALSTACK_ENDPOINT} lambda delete-function \
    --function-name ${FUNCTION_NAME} \
    --region ${AWS_REGION} 2>/dev/null || echo "Function doesn't exist yet"

# Step 7: Create Lambda function
echo ""
echo "🎯 Creating Lambda function..."
aws --endpoint-url=${LOCALSTACK_ENDPOINT} lambda create-function \
    --function-name ${FUNCTION_NAME} \
    --package-type Image \
    --code ImageUri=${ECR_URI} \
    --role ${ROLE_ARN} \
    --timeout 900 \
    --memory-size 2048 \
    --environment "Variables={
        AGE_GROUP=U14,
        DIVISION=Northeast,
        START_OFFSET=1,
        END_OFFSET=1,
        MISSING_TABLE_API_BASE_URL=http://host.docker.internal:8000,
        MISSING_TABLE_API_TOKEN=test-token,
        LOG_LEVEL=INFO,
        ENABLE_TEAM_CACHE=true,
        CACHE_REFRESH_ON_MISS=true,
        CACHE_PRELOAD_TIMEOUT=30
    }" \
    --region ${AWS_REGION}

echo ""
echo "✅ Lambda function deployed successfully!"
echo ""
echo "📝 Function details:"
echo "   Name: ${FUNCTION_NAME}"
echo "   Region: ${AWS_REGION}"
echo "   Image: ${ECR_URI}"
echo "   Memory: 2048 MB"
echo "   Timeout: 900 seconds (15 minutes)"
echo ""
echo "🧪 Test the function with:"
echo "   ./scripts/invoke_lambda_localstack.sh"
