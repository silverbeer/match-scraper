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

# Basic scrape (U14 Northeast, last 7 days)
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
  -n, --days INTEGER       Days to look back [default: 7]
  -c, --club TEXT          Filter by specific club
  --competition TEXT       Filter by specific competition
  -u, --upcoming          Show only upcoming games
  -s, --stats             Show detailed statistics
  -q, --quiet             Minimal output for scripts
  -v, --verbose           Show detailed logs and full error traces
  -l, --limit INTEGER     Max matches to display [default: 1]
```

**Examples:**
```bash
# Basic scrape (shows 1 match by default)
uv run mls-scraper scrape

# Show 10 matches from U16 Southwest
uv run mls-scraper scrape -a U16 -d Southwest -l 10

# U16 Southwest, last 14 days with stats, show 5 matches
uv run mls-scraper scrape -a U16 -d Southwest -n 14 --stats -l 5

# Only upcoming U15 games, show 3
uv run mls-scraper scrape -a U15 --upcoming -l 3

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
  -n, --days INTEGER       Days to look ahead [default: 14]
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

### `config` - Show available options
Displays all available age groups, divisions, and usage examples.

```bash
uv run mls-scraper config
```

### `demo` - Preview with sample data
Shows how the CLI looks with sample data (no scraping required).

```bash
uv run mls-scraper demo
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

### Environment Variables
```bash
export LOG_LEVEL=WARNING              # Logging level for CLI
export MISSING_TABLE_API_URL=...      # API endpoint (if using API)
export MISSING_TABLE_API_KEY=...      # API key (if using API)
```

### Default Settings
- Age Group: U14
- Division: Northeast
- Days to look back: 7
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

### Scripting Examples

**Check for upcoming games:**
```bash
#!/bin/bash
GAMES=$(uv run mls-scraper upcoming -l 3 --quiet)
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
# Check today's games
uv run mls-scraper scrape -n 1 --upcoming --quiet | \
    grep "$(date +%m/%d)" || echo "No games today"
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
GAMES=$(uv run mls-scraper upcoming -l 5 --quiet)
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

**No matches found:**
- Try different age groups or divisions
- Increase the number of days to look back
- Check if the MLS website is accessible
- Use demo mode to verify CLI is working

**Browser errors:**
- Install Playwright browsers: `uv run playwright install`
- Check internet connection
- Try running with different configurations

**Connection/metrics errors:**
- Ignore "Connection refused" errors on port 4318 (metrics server not running - this is normal)
- Use `--verbose` flag to see full error details when troubleshooting
- Network errors are shown with user-friendly messages by default

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

For issues or feature requests, check the project repository or create an issue.