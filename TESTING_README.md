# MLS Match Scraper - Testing Guide

This guide explains how to test the MLS match scraper functionality to verify that parsing and extraction is working correctly.

## Testing Scripts

### 1. Dry Run Test (`scripts/test_scraping_dry_run.py`)
**Purpose**: Verify setup and configuration without browser automation
**Usage**: `uv run python scripts/test_scraping_dry_run.py`

This script tests:
- ✅ Dependencies are installed
- ✅ Configuration loading and validation
- ✅ Scraper initialization
- ✅ Environment setup

### 2. Parsing Tests (`scripts/test_parsing_only.py`)
**Purpose**: Test match parsing logic without browser automation
**Usage**: `uv run python scripts/test_parsing_only.py`

This script tests:
- ✅ Date parsing (MM/DD/YYYY, YYYY-MM-DD, Month DD, YYYY formats)
- ✅ Score parsing (various score formats and status detection)
- ✅ Text parsing (extracting data from raw text)
- ✅ Match object creation

### 3. Full Scraping Test (`scripts/test_scraping_manual.py`)
**Purpose**: Test complete scraping workflow with browser automation
**Usage**: `uv run python scripts/test_scraping_manual.py`

This script tests:
- 🌐 Browser initialization and navigation
- 🔍 Filter application (age group, division, etc.)
- 📅 Date range setting
- ⚽ Match extraction and parsing
- 📊 Metrics collection
- 📝 Detailed match logging

## Testing Workflow

### Step 1: Verify Setup
```bash
uv run python scripts/test_scraping_dry_run.py
```
This should show all ✅ green checkmarks. If you see ❌ red X marks, fix those issues first.

### Step 2: Test Parsing Logic
```bash
uv run python scripts/test_parsing_only.py
```
This verifies that the core parsing algorithms work correctly with sample data.

### Step 3: Test Full Scraping
```bash
uv run python scripts/test_scraping_manual.py
```
This runs the complete workflow including browser automation to scrape real data from the MLS website.

## Understanding the Output

### Detailed Match Logging
When you run the full scraping test, you'll see detailed logs like:

```
=== DISCOVERED MATCHES SUMMARY ===
Total matches: 15
Age group: U14
Division: Northeast
Date range: 2025-09-12 to 2025-09-19

=== SCHEDULED MATCHES (8) ===
SCHEDULED #1: FC Dallas Youth vs Houston Dynamo Academy
  Date: 2025-09-20
  Time: 3:00 PM
  Venue: Toyota Stadium
  Division: Northeast
  Age Group: U14

=== COMPLETED MATCHES (7) ===
COMPLETED #1: Austin FC Academy vs San Antonio FC Youth - 2 - 1
  Date: 2025-09-18
  Time: 10:00 AM
  Venue: St. David's Performance Center
  Division: Northeast
  Age Group: U14

=== MATCH DISCOVERY STATISTICS ===
Total matches: 15
Scheduled matches: 8
Completed matches: 7
In-progress matches: 0
Matches with scores: 7
Matches with venues: 12
Matches with times: 14
Unique teams: 24
```

### What to Look For

#### ✅ Good Signs:
- **Matches found**: Total matches > 0
- **Proper parsing**: Team names look realistic (not garbled)
- **Correct statuses**: Scheduled vs completed matches are properly identified
- **Valid scores**: Completed matches have numeric scores
- **Reasonable dates**: Dates are within the expected range
- **Venue information**: Most matches have venue data

#### ⚠️ Warning Signs:
- **No matches found**: Could indicate website changes or network issues
- **Garbled team names**: Parsing logic may need adjustment
- **Missing scores**: Score extraction might not be working
- **Wrong dates**: Date parsing could be incorrect
- **All matches same status**: Status detection might be broken

#### ❌ Error Signs:
- **Browser errors**: Playwright/browser setup issues
- **Navigation failures**: Website access problems
- **Parsing exceptions**: Code bugs in extraction logic
- **Configuration errors**: Invalid settings

## Troubleshooting

### No Matches Found
1. Check if the MLS website is accessible
2. Verify the date range includes actual matches
3. Try different age groups or divisions
4. Check if website structure has changed

### Parsing Issues
1. Run parsing tests first to isolate the problem
2. Check browser developer tools to see actual HTML structure
3. Update CSS selectors if website layout changed
4. Verify date/score parsing with sample data

### Browser Issues
1. Ensure Playwright browsers are installed: `uv run playwright install`
2. Check if running in headless mode works
3. Try running with `headless=False` for debugging
4. Verify system has required dependencies

### Configuration Issues
1. Check environment variables are set correctly
2. Verify age group and division values are valid
3. Ensure date ranges are reasonable
4. Test with minimal configuration first

## Configuration Options

You can modify the test scripts to try different configurations:

```python
config = ScrapingConfig(
    age_group="U16",        # U13, U14, U15, U16, U17, U18, U19
    division="Southwest",   # Northeast, Southeast, Central, Southwest, etc.
    look_back_days=14,      # Number of days to look back
    club="",               # Specific club filter (empty = all clubs)
    competition="",        # Specific competition filter (empty = all)
    log_level="DEBUG",     # DEBUG, INFO, WARNING, ERROR
)
```

## Next Steps

After verifying that scraping works correctly:

1. **Integration Testing**: Run the existing integration tests
2. **API Integration**: Connect with the missing-table.com API client
3. **Lambda Deployment**: Package for AWS Lambda deployment
4. **Monitoring**: Set up metrics and alerting
5. **Scheduling**: Configure automated execution

## Getting Help

If you encounter issues:

1. Check the detailed logs for specific error messages
2. Run tests in order (dry run → parsing → full scraping)
3. Try with different configurations to isolate problems
4. Verify the MLS website hasn't changed structure
5. Check that all dependencies are properly installed