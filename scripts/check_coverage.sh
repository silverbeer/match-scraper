#!/bin/bash
# Check coverage of newly added code

set -e

echo "🔍 Checking coverage of newly added code..."

# Default comparison branch
COMPARE_BRANCH=${1:-main}

# Run tests with coverage
echo "📊 Running tests with coverage..."
uv run pytest tests/unit/ --cov=src --cov-report=xml --cov-report=term-missing -q

# Check diff coverage
echo "🎯 Checking coverage of changes since $COMPARE_BRANCH..."
uv run diff-cover coverage.xml --compare-branch="$COMPARE_BRANCH" --html-report=diff-cover.html

# Check quality coverage (only new code needs high coverage)
echo "✨ Checking quality coverage (new code only)..."
uv run diff-quality --violations=ruff coverage.xml --compare-branch="$COMPARE_BRANCH"

echo ""
echo "📋 Summary:"
echo "- Full coverage report: coverage.xml"
echo "- Diff coverage HTML: diff-cover.html"
echo "- Open diff-cover.html in browser to see which new lines need tests"
