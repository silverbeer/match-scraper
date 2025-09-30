#!/bin/bash

# Verification script for Lambda deployment setup
# Checks prerequisites and environment before deployment

echo "🔍 Verifying Lambda deployment setup..."
echo ""

# Track if all checks pass
ALL_CHECKS_PASSED=true

# Check 1: Docker
echo "1️⃣  Checking Docker..."
if command -v docker &> /dev/null; then
    echo "   ✅ Docker CLI installed"

    if docker info &> /dev/null; then
        echo "   ✅ Docker daemon is running"
        DOCKER_VERSION=$(docker --version)
        echo "   📦 ${DOCKER_VERSION}"
    else
        echo "   ❌ Docker daemon is not running"
        echo "      Start Docker Desktop or run: sudo systemctl start docker"
        ALL_CHECKS_PASSED=false
    fi
else
    echo "   ❌ Docker is not installed"
    echo "      Install from: https://docs.docker.com/get-docker/"
    ALL_CHECKS_PASSED=false
fi

echo ""

# Check 2: AWS CLI
echo "2️⃣  Checking AWS CLI..."
if command -v aws &> /dev/null; then
    echo "   ✅ AWS CLI installed"
    AWS_VERSION=$(aws --version)
    echo "   📦 ${AWS_VERSION}"
else
    echo "   ❌ AWS CLI is not installed"
    echo "      Install with: brew install awscli (macOS) or see https://aws.amazon.com/cli/"
    ALL_CHECKS_PASSED=false
fi

echo ""

# Check 3: jq
echo "3️⃣  Checking jq..."
if command -v jq &> /dev/null; then
    echo "   ✅ jq installed"
    JQ_VERSION=$(jq --version)
    echo "   📦 ${JQ_VERSION}"
else
    echo "   ❌ jq is not installed"
    echo "      Install with: brew install jq (macOS) or sudo apt install jq (Linux)"
    ALL_CHECKS_PASSED=false
fi

echo ""

# Check 4: Deployment scripts
echo "4️⃣  Checking deployment scripts..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

SCRIPTS=(
    "deploy_lambda_localstack.sh"
    "invoke_lambda_localstack.sh"
    "setup_eventbridge_localstack.sh"
)

for script in "${SCRIPTS[@]}"; do
    if [ -f "${SCRIPT_DIR}/${script}" ]; then
        if [ -x "${SCRIPT_DIR}/${script}" ]; then
            echo "   ✅ ${script} (executable)"
        else
            echo "   ⚠️  ${script} (not executable)"
            echo "      Run: chmod +x scripts/${script}"
        fi
    else
        echo "   ❌ ${script} (missing)"
        ALL_CHECKS_PASSED=false
    fi
done

echo ""

# Check 5: Dockerfile
echo "5️⃣  Checking Dockerfile..."
if [ -f "Dockerfile.lambda" ]; then
    echo "   ✅ Dockerfile.lambda exists"
else
    echo "   ❌ Dockerfile.lambda is missing"
    ALL_CHECKS_PASSED=false
fi

echo ""

# Check 6: Docker Compose file
echo "6️⃣  Checking Docker Compose configuration..."
if [ -f "docker-compose.localstack.yml" ]; then
    echo "   ✅ docker-compose.localstack.yml exists"
else
    echo "   ❌ docker-compose.localstack.yml is missing"
    ALL_CHECKS_PASSED=false
fi

echo ""

# Check 7: Lambda handler
echo "7️⃣  Checking Lambda handler..."
if [ -f "src/lambda_handler.py" ]; then
    echo "   ✅ src/lambda_handler.py exists"

    # Check if it has the main handler function
    if grep -q "def lambda_handler" src/lambda_handler.py; then
        echo "   ✅ lambda_handler function found"
    else
        echo "   ⚠️  lambda_handler function not found"
    fi
else
    echo "   ❌ src/lambda_handler.py is missing"
    ALL_CHECKS_PASSED=false
fi

echo ""

# Summary
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ "$ALL_CHECKS_PASSED" = true ]; then
    echo "✅ All checks passed! Ready for Lambda deployment."
    echo ""
    echo "Next steps:"
    echo "  1. Start LocalStack: docker-compose -f docker-compose.localstack.yml up -d"
    echo "  2. Deploy Lambda: ./scripts/deploy_lambda_localstack.sh"
    echo "  3. Test function: ./scripts/invoke_lambda_localstack.sh"
    echo "  4. Set up schedule: ./scripts/setup_eventbridge_localstack.sh"
else
    echo "❌ Some checks failed. Please fix the issues above before proceeding."
    exit 1
fi
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
