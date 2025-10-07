# Database Fix Guide

This guide explains how to fix existing data in your Supabase database that was incorrectly marked as "completed" with 0-0 scores.

## Problem

Before our fixes, the scraper was posting games with 0-0 scores as "completed" games. This was incorrect because:
- 0-0 scores are often placeholders used by MLS before real scores are posted
- Games should show as "TBD" until real scores are available
- Only games with actual scores should be marked as "completed"

## Solution

We've created a script to fix the existing data in your database. The script will:
1. Find all games with 0-0 scores marked as "completed"
2. Update them to the correct status based on date logic:
   - Games today or in the past → "TBD"
   - Games in the future → "scheduled"
3. Clear the placeholder scores (set to null)

## Usage

### Option 1: Interactive Script (Recommended)

```bash
./scripts/fix-database.sh
```

This will:
- Load your environment variables from `.env.dev`
- Show you what would be changed (dry run)
- Ask for confirmation before making changes

### Option 2: Direct Python Script

```bash
# Dry run (see what would be changed)
python3 scripts/fix-supabase-data.py --dry-run

# Execute changes
python3 scripts/fix-supabase-data.py --execute
```

### Option 3: With Custom API Settings

```bash
python3 scripts/fix-supabase-data.py \
  --api-url "https://your-api-url.com" \
  --api-token "your-api-token" \
  --dry-run
```

## Environment Variables

The script needs these environment variables:

```bash
MISSING_TABLE_API_BASE_URL=https://your-api-url.com
MISSING_TABLE_API_TOKEN=your-api-token
```

You can set these in:
1. `.env.dev` file (recommended)
2. Environment variables
3. Command line arguments

## What Gets Fixed

The script identifies games that match these criteria:
- `home_score = 0`
- `away_score = 0`
- `status = "completed"`

These games will be updated to:
- `status = "TBD"` (for games today or in the past)
- `status = "scheduled"` (for games in the future)
- `home_score = null`
- `away_score = null`

## Safety Features

- **Dry run by default**: Shows what would be changed without making changes
- **Confirmation required**: Asks for confirmation before executing
- **Detailed logging**: Shows exactly what's being changed
- **Error handling**: Continues processing even if some updates fail

## Example Output

```
🔧 MLS Match Scraper - Database Fix Tool
================================================
✓ Environment configured
  API URL: https://dev.missingtable.com
  API Token: abc1234567...

Found 5 games with 0-0 scores marked as completed

┌────┬────────────┬─────────────────┬─────────────────┬───────────────┬───────────┐
│ ID │ Date       │ Home Team       │ Away Team       │ Current Status│ New Status│
├────┼────────────┼─────────────────┼─────────────────┼───────────────┼───────────┤
│ 1  │ 2025-10-04 │ Team A          │ Team B          │ completed     │ TBD       │
│ 2  │ 2025-10-05 │ Team C          │ Team D          │ completed     │ scheduled │
└────┴────────────┴─────────────────┴─────────────────┴───────────────┴───────────┘

DRY RUN: Would fix 5 games

To execute these changes, run:
  python scripts/fix-supabase-data.py --execute
```

## After Running the Fix

Once you've fixed the existing data:
1. **Future scrapes will work correctly** - no more 0-0 completed games
2. **Games without scores will show as TBD** - correct behavior
3. **Only real scores will be posted** - improved data quality

## Troubleshooting

### "No games with placeholder scores found"
This means your database is already clean! No action needed.

### "Error loading configuration"
Make sure your environment variables are set correctly:
```bash
export MISSING_TABLE_API_BASE_URL=https://your-api-url.com
export MISSING_TABLE_API_TOKEN=your-api-token
```

### "Failed to update game"
Some games might fail to update due to API issues. The script will continue processing other games and show a summary at the end.

## Going Forward

After running this fix:
- The scraper will continue to work correctly
- New games will have proper status logic
- No more 0-0 completed games will be created
- Your data will be clean and accurate
