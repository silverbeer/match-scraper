#!/bin/bash

# Test script to run scraper in headful mode to debug calendar navigation
# This allows us to visually see what's happening in the browser

echo "Running scraper in HEADFUL mode to test calendar navigation..."
echo "Date range: September 1-30, 2025"
echo "Club: New England"
echo "Age Group: U14"
echo ""

uv run python -m src.cli.main scrape \
  --club "New England" \
  --age-group "U14" \
  --from 2025-09-01 \
  --to 2025-09-30 \
  --no-headless \
  --timeout 60

echo ""
echo "Test complete!"
