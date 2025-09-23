# E2E Testing Guide for Match Extraction (Task 8)

This guide explains how to run comprehensive end-to-end tests for the match extraction functionality with a visible browser for debugging and verification.

## Quick Start

### First Time Setup
```bash
# Install Playwright browsers (required for e2e tests)
uv run playwright install

# Or install just Chromium (smaller download)
uv run playwright install chromium
```

### Run with Visible Browser (Recommended for Review)
```bash
# Option 1: Run via uv script entry point (recommended)
uv run run-e2e-test --visible

# Option 2: Run the script directly
uv run scripts/run_e2e_test.py --visible

# Run with slow motion for better observation
uv run run-e2e-test --visible --slow 2000

# Run with specific filters
uv run run-e2e-test --visible --age-group U15 --division Southeast
```

### Run with pytest
```bash
# Run the comprehensive e2e test with visible browser
E2E_VISIBLE=true uv run pytest tests/e2e/test_match_extraction_e2e.py::test_full_match_extraction_workflow_visible -v -s

# Run all e2e tests in headless mode
uv run pytest tests/e2e/test_match_extraction_e2e.py -v

# Run specific test with markers
uv run pytest tests/e2e/test_match_extraction_e2e.py -m e2e -v
```

## Test Options

### Script Options
- `--visible`: Run with visible browser (great for debugging)
- `--headless`: Run in headless mode (faster, good for CI)
- `--debug`: Step-by-step execution with manual pauses
- `--performance`: Run performance benchmarks
- `--slow N`: Add N milliseconds delay between actions
- `--age-group GROUP`: Test specific age group (U13-U19)
- `--division DIV`: Test specific division
- `--look-back-days N`: Number of days to look back for matches

### Environment Variables
- `E2E_VISIBLE=true`: Force visible browser
- `E2E_SLOW_MO=1000`: Add slow motion delay

## Test Scenarios

### 1. Full Workflow Test (Recommended for Review)
```bash
# Using entry point (recommended)
uv run run-e2e-test --visible --slow 1500

# Or using script directly
uv run scripts/run_e2e_test.py --visible --slow 1500
```

This test runs the complete workflow:
1. ✅ Navigate to MLS website
2. ✅ Discover available filter options
3. ✅ Apply age group and division filters
4. ✅ Set date range filter
5. ✅ Extract match data from results
6. ✅ Validate and display results
7. ✅ Keep browser open for 10 seconds for inspection

### 2. Debug Mode (Step-by-Step)
```bash
uv run scripts/run_e2e_test.py --debug
```

Interactive debug mode that pauses at each step:
- Manual control over test progression
- Detailed logging of each operation
- Browser console logging enabled
- Perfect for troubleshooting issues

### 3. Performance Testing
```bash
uv run scripts/run_e2e_test.py --performance
```

Runs multiple test scenarios to measure:
- Total extraction time
- Matches extracted per second
- Performance across different filters

### 4. Headless CI Mode
```bash
uv run scripts/run_e2e_test.py --headless
```

Fast headless execution suitable for CI/CD pipelines.

## What the Tests Validate

### Browser Automation
- ✅ Successful navigation to MLS website
- ✅ Page loading and network idle detection
- ✅ Element interaction (clicks, form fills)
- ✅ Error handling for network issues

### Filter Application
- ✅ Discovery of available filter options
- ✅ Age group filter application
- ✅ Division filter application
- ✅ Club and competition filters (if available)
- ✅ Filter validation and error handling

### Calendar Interaction
- ✅ Calendar widget opening
- ✅ Date range selection
- ✅ Date navigation (month/year)
- ✅ Filter application
- ✅ Graceful handling when calendar not available

### Match Data Extraction
- ✅ HTML table parsing
- ✅ Match card parsing (fallback)
- ✅ Data mapping to Match objects
- ✅ Score extraction for completed matches
- ✅ Status detection (scheduled/in-progress/completed)
- ✅ Date/time parsing
- ✅ Team name extraction
- ✅ Venue information extraction

### Data Quality Validation
- ✅ Required fields present (teams, date, status)
- ✅ Data consistency (completed matches have scores)
- ✅ Proper age group and division assignment
- ✅ Reasonable date ranges
- ✅ Team name uniqueness per match
- ✅ Score format validation

## Expected Results

### Successful Test Output
```
=== STARTING MATCH EXTRACTION E2E TEST ===
Configuration:
  Visible browser: True
  Age group: U14
  Division: Northeast
  Look back days: 30

Step 1: Navigating to MLS website...
✓ Successfully navigated to MLS website

Step 2: Applying filters...
  Available age groups: 7
  Available divisions: 9
✓ Filters applied successfully

Step 3: Setting date range...
✓ Date range filter applied successfully

Step 4: Extracting match data...
✓ Extracted 15 matches

=== MATCH EXTRACTION RESULTS ===
Total matches found: 15
  Scheduled: 8
  Completed: 7
  In Progress: 0

=== SAMPLE MATCHES ===
Match 1:
  Teams: FC Dallas vs Atlanta United
  Date: 2024-12-20 15:00
  Status: scheduled
  Venue: Toyota Stadium

Match 2:
  Teams: LAFC vs Seattle Sounders
  Date: 2024-12-18 14:00
  Status: completed
  Score: 2 - 1
```

### Data Quality Metrics
- **Team Names**: 100% of matches should have both home and away teams
- **Dates**: 100% of matches should have valid dates
- **Status Consistency**: Completed matches should have scores, scheduled matches should not
- **Age Group/Division**: All matches should match the applied filters

## Testing Playwright Installation

### **Method 1: Use our simple test script (Recommended)**
```bash
# Quick test that doesn't hit external websites
uv run scripts/test_playwright.py
```
This will test Playwright installation, browser launch, and basic functionality.

### **Method 2: Direct Playwright commands**
```bash
# Check Playwright version
uv run playwright --version

# Test browser launch (will open and close quickly)
uv run python -c "
import asyncio
from playwright.async_api import async_playwright

async def test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        print('✅ Browser launched successfully!')
        await browser.close()

asyncio.run(test())
"
```

### **Method 3: Use the e2e script**
```bash
# This will tell you immediately if Playwright is set up correctly
uv run run-e2e-test --headless --look-back-days 1
```
If Playwright isn't installed, you'll see the setup message. If it is installed, the test will start running.

## Troubleshooting

### Common Issues

1. **"Executable doesn't exist" or Playwright errors**
   ```bash
   # Fix: Install Playwright browsers
   uv run playwright install
   ```

2. **No matches found**
   - Normal if no games scheduled in the date range
   - Try different age group/division combinations
   - Check if website structure has changed

3. **Network/timeout errors**
   - Check your internet connection
   - Try again in a few minutes
   - Use `--headless` flag if having display issues

4. **Filter application fails**
   - Website may have different selectors
   - Check browser console for JavaScript errors
   - Run in debug mode to inspect elements

5. **Date range filter fails**
   - Some pages may not have date filters
   - Test continues without date filter
   - Check calendar widget availability

6. **Extraction returns empty results**
   - Website may use different HTML structure
   - Check for loading indicators
   - Verify results container selectors

### Debug Commands
```bash
# Run with maximum debugging
uv run scripts/run_e2e_test.py --debug --visible --slow 3000

# Check specific filter combination
uv run scripts/run_e2e_test.py --visible --age-group U16 --division Central

# Test performance
uv run scripts/run_e2e_test.py --performance
```

## Integration with Development Workflow

### Before Code Review
```bash
# Run comprehensive test with visible browser
uv run scripts/run_e2e_test.py --visible --slow 1000
```

### During Development
```bash
# Quick headless test
uv run scripts/run_e2e_test.py --headless

# Debug specific issues
uv run scripts/run_e2e_test.py --debug
```

### CI/CD Pipeline
```bash
# Fast headless validation
uv run pytest tests/e2e/test_match_extraction_e2e.py::test_match_extraction_headless -v
```

## Files Created for Task 8

### Core Implementation
- `src/scraper/match_extraction.py` - Main extraction logic
- `tests/unit/test_match_extraction.py` - Unit tests
- `tests/e2e/test_match_extraction_e2e.py` - E2E tests

### Testing Infrastructure
- `scripts/run_e2e_test.py` - Test runner script
- `E2E_TESTING_README.md` - This documentation

### Key Features
- **Robust HTML parsing** with multiple fallback strategies
- **Comprehensive error handling** for network and parsing issues
- **Flexible selector system** to handle different website layouts
- **Data validation** to ensure match quality
- **Performance monitoring** and optimization
- **Visual debugging** capabilities for development

### **Quick Start for Review**
```bash
# Run with visible browser and slow motion for easy observation (recommended)
uv run run-e2e-test --visible --slow 1500

# Or run the script directly
uv run scripts/run_e2e_test.py --visible --slow 1500

# Or run the pytest version
E2E_VISIBLE=true uv run pytest tests/e2e/test_match_extraction_e2e.py::test_full_match_extraction_workflow_visible -v -s
```

The implementation is production-ready and includes extensive testing to ensure reliability in the AWS Lambda environment.
