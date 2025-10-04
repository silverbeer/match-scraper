#!/bin/bash

# Fix Supabase Database Script
# This script fixes games that were incorrectly marked as "completed" with 0-0 scores

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🔧 MLS Match Scraper - Database Fix Tool${NC}"
echo "================================================"

# Check if we're in the right directory
if [ ! -f "scripts/fix-supabase-data.py" ]; then
    echo -e "${RED}Error: Please run this script from the project root directory${NC}"
    exit 1
fi

# Check if .env.dev exists
if [ ! -f ".env.dev" ]; then
    echo -e "${YELLOW}Warning: .env.dev file not found${NC}"
    echo "Please create .env.dev with your API configuration:"
    echo "  MISSING_TABLE_API_BASE_URL=https://your-api-url.com"
    echo "  MISSING_TABLE_API_TOKEN=your-api-token"
    echo ""
    echo "Or set these environment variables:"
    echo "  export MISSING_TABLE_API_BASE_URL=https://your-api-url.com"
    echo "  export MISSING_TABLE_API_TOKEN=your-api-token"
    echo ""
    read -p "Continue anyway? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Load environment variables if .env.dev exists
if [ -f ".env.dev" ]; then
    echo -e "${BLUE}Loading environment from .env.dev...${NC}"
    set -a
    source .env.dev
    set +a
fi

# Check required environment variables
if [ -z "$MISSING_TABLE_API_BASE_URL" ] || [ -z "$MISSING_TABLE_API_TOKEN" ]; then
    echo -e "${RED}Error: Missing required environment variables${NC}"
    echo "Please set:"
    echo "  MISSING_TABLE_API_BASE_URL"
    echo "  MISSING_TABLE_API_TOKEN"
    exit 1
fi

echo -e "${GREEN}✓ Environment configured${NC}"
echo "  API URL: $MISSING_TABLE_API_BASE_URL"
echo "  API Token: ${MISSING_TABLE_API_TOKEN:0:10}..."

echo ""
echo -e "${YELLOW}This script will fix games that were incorrectly marked as 'completed' with 0-0 scores.${NC}"
echo -e "${YELLOW}These games will be updated to 'TBD' or 'scheduled' based on their date.${NC}"
echo ""

# Show options
echo "Options:"
echo "  1. Dry run (show what would be changed)"
echo "  2. Execute changes (modify database)"
echo "  3. Exit"
echo ""

read -p "Choose option (1-3): " -n 1 -r
echo

case $REPLY in
    1)
        echo -e "${BLUE}Running dry run...${NC}"
        python3 scripts/fix-supabase-data.py --dry-run
        ;;
    2)
        echo -e "${RED}WARNING: This will modify your database!${NC}"
        read -p "Are you sure? (yes/no): " -r
        if [[ $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
            echo -e "${BLUE}Executing changes...${NC}"
            python3 scripts/fix-supabase-data.py --execute
        else
            echo -e "${YELLOW}Operation cancelled${NC}"
        fi
        ;;
    3)
        echo -e "${YELLOW}Exiting...${NC}"
        exit 0
        ;;
    *)
        echo -e "${RED}Invalid option${NC}"
        exit 1
        ;;
esac

echo ""
echo -e "${GREEN}✅ Database fix completed!${NC}"
