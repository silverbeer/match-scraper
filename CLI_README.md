# ⚽ MLS Match Scraper CLI

A beautiful command-line interface for scraping and displaying MLS match data with rich formatting, colors, and interactive features.

## ✨ Features

- 🎨 **Beautiful terminal output** with colors, tables, and emojis
- 🔍 **Multiple display modes** - full tables, upcoming games, statistics
- 🎮 **Interactive mode** for guided configuration
- ⚡ **Fast and flexible** filtering by age group, division, club, competition
- 📊 **Rich statistics** and match analysis
- 🤖 **Script-friendly** quiet mode for automation
- 🎭 **Demo mode** to preview the interface
- 🐛 **Debug mode** for troubleshooting scraper issues
- 🔍 **Inspector mode** for manual page analysis

## 🚀 Quick Start

### Installation
The CLI is automatically available after installing the project:

```bash
# Install dependencies
uv sync

# Test with demo data
uv run mls-scraper demo

# Or use the shortcut script
./scripts/mls demo
```

### Basic Usage

```bash
# Show help
uv run mls-scraper --help

# Basic scrape (U14 Northeast, next 3 days)
uv run mls-scraper scrape

# Specific age group and division
uv run mls-scraper scrape -a U16 -d Southwest

# Show upcoming games only
uv run mls-scraper upcoming

# Interactive mode
uv run mls-scraper interactive
```

## 📋 Commands

### `scrape` - Main scraping command
Scrapes match data and displays in a beautiful table format.

```bash
uv run mls-scraper scrape [OPTIONS]

Options:
  -a, --age-group TEXT     Age group (U13-U19) [default: U14]
  -d, --division TEXT      Division [default: Northeast]
  -n, --days INTEGER       Days to look ahead for upcoming matches [default: 3]
  -c, --club TEXT          Filter by specific club
  --competition TEXT       Filter by specific competition
  -u, --upcoming          Show only upcoming games
  -s, --stats             Show detailed statistics
  -q, --quiet             Minimal output for scripts
  -v, --verbose           Show detailed logs and full error traces
  -l, --limit INTEGER     Maximum number of matches to display [default: 0]
```

**Examples:**
```bash
# Basic scrape (shows all matches found)
uv run mls-scraper scrape

# Show 10 matches from U16 Southwest
uv run mls-scraper scrape -a U16 -d Southwest -l 10

# U16 Southwest, next 14 days with stats, show 5 matches
uv run mls-scraper scrape -a U16 -d Southwest -n 14 --stats -l 5

# Only upcoming U15 games, show 3
uv run mls-scraper scrape -a U15 --upcoming -l 3

# Run in non-headless mode for debugging
uv run mls-scraper scrape --no-headless

# Quiet mode for scripting
uv run mls-scraper scrape --quiet

# Verbose mode for debugging
uv run mls-scraper scrape --verbose
```

### `upcoming` - Quick upcoming games view
Shows upcoming games in a clean, focused format.

```bash
uv run mls-scraper upcoming [OPTIONS]

Options:
  -a, --age-group TEXT     Age group [default: U14]
  -d, --division TEXT      Division [default: Northeast]
  -n, --days INTEGER       Days to look ahead [default: 3]
  -l, --limit INTEGER      Max games to show [default: 10]
```

**Examples:**
```bash
# Next 10 U14 Northeast games
uv run mls-scraper upcoming

# Next 5 U16 Southwest games
uv run mls-scraper upcoming -a U16 -d Southwest -l 5
```

### `interactive` - Guided experience
Interactive mode with prompts for all configuration options.

```bash
uv run mls-scraper interactive
```

### `config` - Configuration management
Comprehensive environment variable and configuration management.

```bash
# Show current configuration status
uv run mls-scraper config show

# Interactive setup of all environment variables
uv run mls-scraper config setup

# Set a specific environment variable
uv run mls-scraper config set MISSING_TABLE_API_TOKEN your-token-here

# Validate current configuration
uv run mls-scraper config validate

# Show available CLI options and examples
uv run mls-scraper config options
```

**Environment Variable Management:**
- `show` - Display current environment configuration and status
- `setup` - Interactive guided setup of all required and optional variables
- `set` - Set individual environment variables
- `validate` - Check if all required variables are properly configured
- `options` - Show available age groups, divisions, and usage examples

### `demo` - Preview with sample data
Shows how the CLI looks with sample data (no scraping required).

```bash
uv run mls-scraper demo
```

### `test-quiet` - Test quiet mode
Shows how quiet mode output looks for scripting purposes.

```bash
uv run mls-scraper test-quiet
```

### `debug` - Debug the scraper
Helps diagnose issues with the scraping process by running individual steps.

```bash
# Debug all steps
uv run mls-scraper debug

# Debug specific step
uv run mls-scraper debug --step consent

# Debug with visible browser
uv run mls-scraper debug --no-headless
```

**Available debug steps:**
- `url` - Test URL accessibility
- `browser` - Test browser initialization
- `navigate` - Test navigation to MLS page
- `consent` - Test consent banner handling
- `filters` - Test filter discovery and application
- `extract` - Test match extraction
- `inspect` - Inspect page elements

### `inspect` - Manual page inspection
Opens browser and navigates to MLS page for manual inspection of pop-ups, overlays, or blocking elements.

```bash
# Open browser for manual inspection
uv run mls-scraper inspect

# Inspect with visible browser and extended timeout
uv run mls-scraper inspect --no-headless --timeout 300
```

## 🎯 Available Options

### Age Groups
- U13, U14, U15, U16, U17, U18, U19

### Divisions
- Northeast, Southeast, Central, Southwest, Northwest
- Mid-Atlantic, Great Lakes, Texas, California

## 🛠️ Shortcut Script

For convenience, use the `./scripts/mls` wrapper:

```bash
# Shortcuts
./scripts/mls games -a U16 -d Southwest    # Same as 'scrape'
./scripts/mls upcoming -l 5                # Show upcoming games
./scripts/mls interactive                  # Interactive mode
./scripts/mls demo                         # Demo mode
./scripts/mls config                       # Show config options
./scripts/mls help                         # Show shortcuts help
```

## 📊 Output Examples

### Full Match Table
```
╭─────────────────────────────────────────────────────────── ⚽ Matches Found (15) ──────────────────────────────────────────────────────────╮
│  Date          Time      Home Team               Away Team               Score/Status  Venue                    │
│  09/18/2025    10:00 AM  Austin FC Academy       San Antonio FC Youth       2 - 1      St. David's Performance  │
│  09/19/2025    1:30 PM   Real Salt Lake Academy  Colorado Rapids Youth     🔄 1 - 0    Zions Bank Training      │
│  09/20/2025    3:00 PM   FC Dallas Youth         Houston Dynamo Academy  ⏰ Scheduled  Toyota Stadium           │
╰─────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

### Statistics Panel
```
╭─────────────────────────────────────────────────────────────── 📊 Statistics ───────────────────────────────────────────────────────────────╮
│  Total Matches    15  100%                                                                                       │
│  📅 Scheduled     8    53%                                                                                       │
│  ✅ Completed     7    47%                                                                                       │
│  ⚽ With Scores   7    47%                                                                                       │
│  🏟️  With Venues   12   80%                                                                                       │
│  👥 Unique Teams  24                                                                                             │
╰───────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

### Upcoming Games
```
🔮 Next 5 Upcoming Games:
1. FC Dallas Youth vs Houston Dynamo Academy
   📅 Saturday, September 20 at 3:00 PM
   🏟️  Toyota Stadium

2. Austin FC Academy vs Real Salt Lake Academy
   📅 Sunday, September 21 at 2:00 PM
   🏟️  St. David's Performance Center
```

## 🔧 Configuration

### Quick Setup
The easiest way to configure your environment variables:

```bash
# Interactive setup - guides you through all required variables
uv run mls-scraper config setup

# Check if everything is configured correctly
uv run mls-scraper config validate

# View current configuration
uv run mls-scraper config show
```

### Manual Environment Variables
If you prefer to set environment variables manually:

```bash
export LOG_LEVEL=WARNING                  # Logging level for CLI
export MISSING_TABLE_API_BASE_URL=...     # API endpoint (if using API)
export MISSING_TABLE_API_TOKEN=...        # API token (if using API)
```

**Required Variables:**
- `MISSING_TABLE_API_BASE_URL` - API endpoint for missing-table service
- `MISSING_TABLE_API_TOKEN` - Your service account (SA) token

**Optional Variables:**
- `LOG_LEVEL` - Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- `AGE_GROUP` - Default age group (U13-U19)
- `DIVISION` - Default division
- `LOOK_BACK_DAYS` - Default number of days to look ahead

### Default Settings
- Age Group: U14
- Division: Northeast
- Days to look ahead: 3
- Log Level: WARNING (quiet for CLI use)

## 🎨 Customization

### Colors and Styling
The CLI uses Rich for formatting with these color schemes:
- **Green**: Home teams, completed matches
- **Red**: Away teams
- **Yellow**: Scores, in-progress matches
- **Cyan**: Dates, configuration labels
- **Blue**: Venues, headers
- **Magenta**: Statistics headers

### Quiet Mode
Use `--quiet` for script-friendly output:
```bash
uv run mls-scraper scrape --quiet
# Output:
✅ 09/18 Austin FC Academy vs San Antonio FC Youth (2 - 1)
🔄 09/19 Real Salt Lake Academy vs Colorado Rapids Youth (1 - 0)
⏰ 09/20 FC Dallas Youth vs Houston Dynamo Academy
```

## 🚀 Advanced Usage

### Configuration Management

**First-time setup:**
```bash
# Quick interactive setup
uv run mls-scraper config setup

# Set your SA token specifically
uv run mls-scraper config set MISSING_TABLE_API_TOKEN your-token-here

# Verify everything is configured
uv run mls-scraper config validate
```

**Check configuration status:**
```bash
# View current config
uv run mls-scraper config show

# Validate config before running scrapes
uv run mls-scraper config validate && uv run mls-scraper scrape
```

### Scripting Examples

**Check for upcoming games:**
```bash
#!/bin/bash
GAMES=$(uv run mls-scraper upcoming -l 3)
if [ -n "$GAMES" ]; then
    echo "Upcoming games found:"
    echo "$GAMES"
else
    echo "No upcoming games"
fi
```

**Daily game check:**
```bash
#!/bin/bash
# Check next 3 days for games
uv run mls-scraper scrape -n 3 --upcoming --quiet | \
    grep "$(date +%m/%d)" || echo "No games in next 3 days"
```

**Multi-division check:**
```bash
#!/bin/bash
for division in Northeast Southwest Central; do
    echo "=== $division ==="
    uv run mls-scraper scrape -d "$division" --upcoming --quiet
    echo
done
```

### Integration with Other Tools

**Send to Slack/Discord:**
```bash
GAMES=$(uv run mls-scraper upcoming -l 5)
curl -X POST -H 'Content-type: application/json' \
    --data "{\"text\":\"Upcoming MLS Games:\n$GAMES\"}" \
    YOUR_WEBHOOK_URL
```

**Save to file:**
```bash
uv run mls-scraper scrape --stats > daily_games_$(date +%Y%m%d).txt
```

## 🐛 Troubleshooting

### Common Issues

**Command not found:**
```bash
# Make sure you're in the project directory and using uv
cd /path/to/mls-match-scraper
uv run mls-scraper --help
```

**Configuration issues:**
```bash
# Check what's missing
uv run mls-scraper config validate

# Quick setup if variables are missing
uv run mls-scraper config setup

# View current status
uv run mls-scraper config show
```

**No matches found:**
- Try different age groups or divisions
- Increase the number of days to look ahead
- Check if the MLS website is accessible
- Use demo mode to verify CLI is working

**Browser errors:**
- Install Playwright browsers: `uv run playwright install`
- Check internet connection
- Try running with different configurations
- Use debug mode: `uv run mls-scraper debug --no-headless`
- Use inspector mode: `uv run mls-scraper inspect --no-headless`

**Connection/metrics errors:**
- Ignore "Connection refused" errors on port 4318 (metrics server not running - this is normal)
- Use `--verbose` flag to see full error details when troubleshooting
- Network errors are shown with user-friendly messages by default
- Use `uv run mls-scraper debug` for step-by-step diagnostics

### Debug Mode
Use the verbose flag for detailed logging and full error traces:
```bash
uv run mls-scraper scrape --verbose
```

Or set environment variable:
```bash
export LOG_LEVEL=DEBUG
uv run mls-scraper scrape
```

## 🎯 Tips & Tricks

1. **Use shortcuts**: `./scripts/mls` is faster than `uv run mls-scraper`
2. **Bookmark common commands**: Create aliases for your favorite configurations
3. **Use quiet mode for scripts**: Perfect for automation and notifications
4. **Try interactive mode**: Great for exploring different options
5. **Check demo first**: Verify the CLI works before running real scrapes
6. **Combine with other tools**: Pipe output to grep, awk, or notification systems

## 🔮 Future Enhancements

Potential future features:
- 📱 **Watch mode**: Continuously monitor for new games
- 🔔 **Notifications**: Desktop/mobile alerts for game updates
- 📈 **Trends**: Historical analysis and team performance
- 🗓️ **Calendar export**: Export to Google Calendar, iCal
- 🎯 **Favorites**: Save favorite teams and get targeted updates
- 🌐 **Web dashboard**: Companion web interface

---

**Enjoy using the MLS Match Scraper CLI!** ⚽✨

Built with [Typer](https://typer.tiangolo.com/) and [Rich](https://rich.readthedocs.io/) for a beautiful command-line experience.

For issues or feature requests, check the project repository or create an issue.
