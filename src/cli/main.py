#!/usr/bin/env python3
"""
MLS Match Scraper CLI - Beautiful terminal interface for MLS match data.

A command-line tool for scraping and displaying MLS match information with
rich formatting and interactive features.
"""

import asyncio
import atexit
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Literal, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.text import Text

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.cli.env_config import (  # noqa: E402
    display_current_config,
    interactive_setup,
    set_variable,
    validate_config,
)
from src.models.audit import RunMetadata, RunSummary  # noqa: E402
from src.scraper.config import ScrapingConfig  # noqa: E402
from src.scraper.mls_scraper import MLSScraper, MLSScraperError  # noqa: E402
from src.scraper.models import Match  # noqa: E402
from src.utils.audit_logger import AuditLogger  # noqa: E402
from src.utils.division_lookup import get_division_id_for_league  # noqa: E402
from src.utils.match_comparison import MatchComparison  # noqa: E402

# Initialize Rich console and Typer app
# Respect NO_COLOR env var for cleaner container logs in Kubernetes
# When NO_COLOR is set, disable colors AND disable forced terminal mode
# This ensures clean JSON logs in container environments
use_rich = os.getenv("NO_COLOR") is None
console = Console(
    no_color=not use_rich,
    force_terminal=use_rich,
)
app = typer.Typer(
    name="mls-scraper",
    help="⚽ MLS Match Scraper - Beautiful terminal interface for MLS match data",
    rich_markup_mode="rich",
)


# Register metrics shutdown handler to ensure metrics are flushed on exit
def _shutdown_metrics() -> None:
    """Shutdown metrics and flush pending data before exit."""
    try:
        from src.utils.metrics import get_metrics

        metrics = get_metrics()
        metrics.shutdown(timeout_seconds=5)
    except Exception:
        # Silently fail - we're exiting anyway
        pass


atexit.register(_shutdown_metrics)

# Configuration defaults
DEFAULT_AGE_GROUP = "U14"
DEFAULT_LEAGUE = "Homegrown"
DEFAULT_DIVISION = "Northeast"
DEFAULT_CONFERENCE = "New England"
DEFAULT_START_OFFSET = 1  # 1 day backward from today = Yesterday
DEFAULT_END_OFFSET = 1  # 1 day forward from today = Tomorrow
DEFAULT_DAYS = 3  # Keep for upcoming command backward compatibility

# Valid options
VALID_AGE_GROUPS = ["U13", "U14", "U15", "U16", "U17", "U18", "U19"]
VALID_LEAGUES = ["Homegrown", "Academy"]
VALID_DIVISIONS = [
    "Northeast",
    "Southeast",
    "Central",
    "Southwest",
    "Northwest",
    "Mid-Atlantic",
    "Great Lakes",
    "Texas",
    "California",
    "Florida",
]
VALID_CONFERENCES = [
    "New England",
    "Northeast",
    "Mid-Atlantic",
    "Southeast",
    "Great Lakes",
    "Central",
    "Texas",
    "Southwest",
    "Northwest",
    "California",
]


# Team name mappings for display
TEAM_NAME_MAPPINGS = {
    "Intercontinental Football Academy of New England": "IFA",
}

# Reverse mapping: CLI short names to full MLS website names
CLI_TO_MLS_CLUB_NAMES = {
    "IFA": "Intercontinental Football Academy of New England",
}


def normalize_team_name_for_display(team_name: str) -> str:
    """Normalize team names for consistent display."""
    return TEAM_NAME_MAPPINGS.get(team_name, team_name)


def apply_league_specific_team_name(team_name: str, league: str) -> str:
    """Apply league-specific suffixes to team names for disambiguation.

    Args:
        team_name: The normalized team name
        league: The league being scraped (e.g., "Homegrown", "Academy")

    Returns:
        Team name with league-specific suffix if needed
    """
    # IFA has teams in both Homegrown and Academy leagues
    # Add "HG" suffix for Homegrown to distinguish from Academy teams
    if team_name == "IFA" and league == "Homegrown":
        return "IFA HG"
    return team_name


def setup_environment(verbose: bool = False) -> None:
    """Set up environment variables for CLI usage."""
    # Load .env file first
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass  # dotenv not available, use system env vars

    log_level = "DEBUG" if verbose else "ERROR"  # Only show errors unless verbose
    os.environ["LOG_LEVEL"] = log_level  # Force set the log level
    os.environ.setdefault("MISSING_TABLE_API_BASE_URL", "http://localhost:8000")
    # Don't override the token if it's already set from .env file
    if not os.getenv("MISSING_TABLE_API_TOKEN"):
        os.environ.setdefault("MISSING_TABLE_API_TOKEN", "")

    # Update the existing logger level immediately
    from src.utils.logger import scraper_logger

    logger = scraper_logger.get_logger()
    logger.setLevel(log_level)


def handle_cli_error(e: Exception, verbose: bool = False) -> None:
    """Handle CLI errors with user-friendly messages."""
    error_message = str(e)

    if "Connection refused" in error_message and "4318" in error_message:
        console.print(
            "[yellow]⚠️  Metrics export failed (this is normal - metrics server not running)[/yellow]"
        )
        if verbose:
            console.print(f"[dim]Full error: {error_message}[/dim]")
    elif "ConnectionError" in str(type(e)) or "Connection" in error_message:
        console.print(
            "[red]❌ Network connection error - please check your internet connection[/red]"
        )
        if verbose:
            console.print(f"[dim]Full error: {error_message}[/dim]")
    elif "TimeoutError" in str(type(e)) or "timeout" in error_message.lower():
        console.print(
            "[red]❌ Operation timed out - the website may be slow or unavailable[/red]"
        )
        if verbose:
            console.print(f"[dim]Full error: {error_message}[/dim]")
    else:
        console.print(f"[red]❌ Error: {error_message}[/red]")

    if verbose:
        console.print("\n[dim]Full stack trace:[/dim]")
        console.print_exception()
    else:
        console.print("[dim]💡 Use --verbose/-v to see full error details[/dim]")


def create_config(
    age_group: str,
    league: str,
    division: str,
    start_offset: int,
    end_offset: int,
    club: str = "",
    competition: str = "",
    conference: str = "",
    verbose: bool = False,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> ScrapingConfig:
    """Create scraping configuration from CLI parameters."""

    # Expand club name if it's a CLI shorthand (e.g., "IFA" -> full name)
    if club and club in CLI_TO_MLS_CLUB_NAMES:
        expanded_club = CLI_TO_MLS_CLUB_NAMES[club]
        if verbose:
            console.print(f"[dim]Expanding club '{club}' to '{expanded_club}'[/dim]")
        club = expanded_club

    # Validate argument combinations and determine date calculation method
    if from_date and to_date:
        # Both absolute dates provided - use them
        try:
            start_date = date.fromisoformat(from_date)
            end_date = date.fromisoformat(to_date)
        except ValueError as e:
            raise ValueError(f"Invalid date format. Use YYYY-MM-DD format: {e}") from e

    elif from_date or to_date:
        # Only one absolute date provided - error
        raise ValueError(
            "Both --from and --to must be provided when using absolute dates"
        )

    else:
        # Use relative offsets
        # Negative offset = past, positive offset = future
        today = date.today()
        start_date = today + timedelta(days=start_offset)  # negative = past days
        end_date = today + timedelta(days=end_offset)  # 0 = today, positive = future

    return ScrapingConfig(
        age_group=age_group,
        league=league,
        club=club,
        competition=competition,
        division=division,
        conference=conference,
        look_back_days=abs(start_offset)
        if start_offset < 0
        else 0,  # Keep for backwards compatibility
        start_date=start_date,
        end_date=end_date,
        missing_table_api_url=os.getenv(
            "MISSING_TABLE_API_BASE_URL", "http://localhost:8000"
        ),
        missing_table_api_key=os.getenv("MISSING_TABLE_API_TOKEN", ""),
        log_level="DEBUG" if verbose else "ERROR",  # Verbose or quiet for CLI
        # Team cache configuration
        enable_team_cache=os.getenv("ENABLE_TEAM_CACHE", "true").lower() == "true",
        cache_refresh_on_miss=os.getenv("CACHE_REFRESH_ON_MISS", "true").lower()
        == "true",
        cache_preload_timeout=int(os.getenv("CACHE_PRELOAD_TIMEOUT", "30")),
    )


def display_header() -> None:
    """Display the application header."""
    if not use_rich:
        return  # Skip header in container environments

    header = Text("⚽ MLS Match Scraper", style="bold blue")
    subtitle = Text("Beautiful terminal interface for MLS match data", style="dim")

    panel = Panel(
        f"{header}\n{subtitle}",
        border_style="blue",
        padding=(1, 2),
    )
    console.print(panel)


def display_config_summary(config: ScrapingConfig) -> None:
    """Display configuration summary."""
    if not use_rich:
        return  # Skip config display in container environments

    config_table = Table(show_header=False, box=None, padding=(0, 1))
    config_table.add_column("Setting", style="cyan")
    config_table.add_column("Value", style="white")

    config_table.add_row("League", config.league)
    config_table.add_row("Age Group", config.age_group)

    # Display division or conference based on league type
    if config.league == "Homegrown":
        config_table.add_row("Division", config.division)
    elif config.league == "Academy":
        config_table.add_row("Conference", config.conference)

    # Display dates in chronological order (earlier to later)
    from_date = min(config.start_date, config.end_date)
    to_date = max(config.start_date, config.end_date)
    config_table.add_row("Date Range", f"{from_date} to {to_date}")
    config_table.add_row("Club Filter", config.club or "All clubs")
    config_table.add_row("Competition Filter", config.competition or "All competitions")

    console.print(Panel(config_table, title="📋 Configuration", border_style="cyan"))


def display_matches_table(matches: list[Match]) -> None:
    """Display matches in a beautiful table format."""
    if not matches:
        console.print(
            Panel(
                "[yellow]No matches found for the specified criteria.[/yellow]",
                title="⚠️  No Results",
                border_style="yellow",
            )
        )
        return

    # Create main matches table
    table = Table(show_header=True, header_style="bold magenta", box=None)
    table.add_column("MLS ID", style="dim", width=10)
    table.add_column("Date", style="cyan", width=12)
    table.add_column("Time", style="dim", width=8)
    table.add_column("Home Team", style="green", min_width=20)
    table.add_column("Away Team", style="red", min_width=20)
    table.add_column("Score/Status", style="yellow", width=12, justify="center")
    table.add_column("Venue", style="blue", min_width=20)

    # Sort matches by date

    sorted_matches = sorted(
        matches, key=lambda m: m.match_datetime if m.match_datetime else datetime.min
    )

    for match in sorted_matches:
        # Format date - handle None dates more robustly
        try:
            if match.match_datetime:
                match_date = match.match_datetime.strftime("%m/%d/%Y")
            else:
                match_date = "Unknown"
        except (AttributeError, ValueError):
            match_date = "Unknown"

        # Format time
        # Extract time from datetime
        try:
            match_time = (
                match.match_datetime.strftime("%I:%M %p")
                if match.match_datetime
                else "TBD"
            )
        except (AttributeError, ValueError):
            match_time = "TBD"

        # Format score/status
        if match.has_score():
            score_text = match.get_score_string()
            if match.match_status == "completed":
                score_status = f"[green]{score_text}[/green]"
            else:
                # Show score even for "scheduled" or "TBD" matches if they have one
                score_status = f"[cyan]{score_text}[/cyan]"
        else:
            # No score available - check if it's TBD vs upcoming
            if match.match_status == "scheduled":
                # For past/current dates, show TBD; for future dates, show Scheduled
                try:
                    today = date.today()
                    match_date_obj = (
                        match.match_datetime.date() if match.match_datetime else today
                    )
                    if match_date_obj <= today:
                        score_status = "[orange1]TBD[/orange1]"
                    else:
                        score_status = "[dim]⏰ Scheduled[/dim]"
                except (AttributeError, ValueError):
                    # Fallback if date handling fails
                    score_status = "[orange1]TBD[/orange1]"
            else:
                score_status = "[dim]⏰ Scheduled[/dim]"

        # Format venue - no truncation
        venue = match.location or "TBD"

        # Format MLS match_id (external ID from MLS website)
        # Note: Internal database ID is assigned later by Celery workers
        match_id_display = (
            match.match_id[-8:] if len(match.match_id) > 8 else match.match_id
        )

        table.add_row(
            match_id_display,
            match_date,
            match_time,
            normalize_team_name_for_display(match.home_team),
            normalize_team_name_for_display(match.away_team),
            score_status,
            venue,
        )

    try:
        console.print(
            Panel(
                table, title=f"⚽ Matches Found ({len(matches)})", border_style="green"
            )
        )
    except Exception:
        # Fallback to simple text output if Rich rendering fails
        console.print(f"\n⚽ Matches Found ({len(matches)}):")
        console.print("=" * 50)
        for match in sorted_matches:
            date_str = (
                match.match_datetime.strftime("%m/%d")
                if match.match_datetime
                else "TBD"
            )
            time_str = (
                match.match_datetime.strftime("%I:%M %p")
                if match.match_datetime
                else "TBD"
            )
            score_str = ""
            if match.has_score():
                score_str = f" ({match.get_score_string()})"
            console.print(
                f"✅ {date_str} {time_str} {normalize_team_name_for_display(match.home_team)} vs {normalize_team_name_for_display(match.away_team)}{score_str}"
            )
        console.print("=" * 50)


def display_statistics(matches: list[Match]) -> None:
    """Display match statistics."""
    if not matches:
        return

    # Calculate statistics
    total_matches = len(matches)
    scheduled_matches = len([m for m in matches if m.match_status == "scheduled"])
    played_matches = len([m for m in matches if m.match_status == "completed"])
    tbd_matches = len([m for m in matches if m.match_status == "tbd"])
    matches_with_scores = len([m for m in matches if m.has_score()])
    matches_with_venues = len([m for m in matches if m.location])
    unique_teams = len(
        set(
            [normalize_team_name_for_display(m.home_team) for m in matches]
            + [normalize_team_name_for_display(m.away_team) for m in matches]
        )
    )

    # Create statistics table
    stats_table = Table(show_header=False, box=None, padding=(0, 1))
    stats_table.add_column("Metric", style="cyan")
    stats_table.add_column("Count", style="white", justify="right")
    stats_table.add_column("Percentage", style="dim", justify="right")

    stats_table.add_row("Total Matches", str(total_matches), "100%")
    stats_table.add_row(
        "📅 Scheduled",
        str(scheduled_matches),
        f"{scheduled_matches / total_matches * 100:.0f}%",
    )
    stats_table.add_row(
        "✅ Played",
        str(played_matches),
        f"{played_matches / total_matches * 100:.0f}%",
    )
    if tbd_matches > 0:
        stats_table.add_row(
            "⏳ Score Pending",
            str(tbd_matches),
            f"{tbd_matches / total_matches * 100:.0f}%",
        )
    stats_table.add_row(
        "⚽ With Scores",
        str(matches_with_scores),
        f"{matches_with_scores / total_matches * 100:.0f}%",
    )
    stats_table.add_row(
        "🏟️  With Venues",
        str(matches_with_venues),
        f"{matches_with_venues / total_matches * 100:.0f}%",
    )
    stats_table.add_row("👥 Unique Teams", str(unique_teams), "")

    console.print(Panel(stats_table, title="📊 Statistics", border_style="magenta"))


def display_upcoming_games(matches: list[Match], limit: int = 5) -> None:
    """Display upcoming games in a special format."""
    from datetime import date

    today = date.today()

    # Filter for truly upcoming games (future scheduled games)
    upcoming = [
        m
        for m in matches
        if m.match_status == "scheduled"
        and m.match_datetime
        and m.match_datetime.date() > today
    ]
    if not upcoming:
        return

    # Sort by date
    upcoming.sort(key=lambda m: m.match_datetime if m.match_datetime else date.max)

    console.print(
        f"\n[bold cyan]🔮 Next {min(limit, len(upcoming))} Upcoming Games:[/bold cyan]"
    )

    for i, match in enumerate(upcoming[:limit], 1):
        match_date = (
            match.match_datetime.strftime("%A, %B %d")
            if match.match_datetime
            else "Date TBD"
        )
        match_time = (
            match.match_datetime.strftime("%I:%M %p")
            if match.match_datetime
            else "Time TBD"
        )
        venue = match.location or "Venue TBD"

        game_text = f"[bold]{i}.[/bold] [green]{normalize_team_name_for_display(match.home_team)}[/green] vs [red]{normalize_team_name_for_display(match.away_team)}[/red]"
        details_text = f"   📅 {match_date} at {match_time}"
        venue_text = f"   🏟️  {venue}"

        console.print(game_text)
        console.print(details_text, style="dim")
        console.print(venue_text, style="dim")
        if i < min(limit, len(upcoming)):
            console.print()


def build_match_dict(match: Match, config: ScrapingConfig) -> dict:
    """Build a queue-ready match dict from a Match object and config.

    Transforms a scraped Match object into the dictionary format expected
    by the RabbitMQ queue and MatchData validation model.

    Args:
        match: Scraped Match object from MLSScraper
        config: Scraping configuration with league/division/conference info

    Returns:
        Dictionary ready for queue submission
    """
    # Determine division/conference name based on league type
    division_name = (
        config.conference
        if config.league == "Academy" and config.conference
        else config.division
        if config.division
        else None
    )

    # Look up division_id using the appropriate league type
    division_id = get_division_id_for_league(
        league=config.league,
        division=config.division,
        conference=config.conference,
    )

    # Normalize team names and apply league-specific suffixes
    home_team_normalized = normalize_team_name_for_display(match.home_team)
    away_team_normalized = normalize_team_name_for_display(match.away_team)
    home_team_final = apply_league_specific_team_name(
        home_team_normalized, config.league
    )
    away_team_final = apply_league_specific_team_name(
        away_team_normalized, config.league
    )

    return {
        "home_team": home_team_final,
        "away_team": away_team_final,
        "match_date": match.match_datetime.date().isoformat()
        if match.match_datetime
        else date.today().isoformat(),
        "match_time": match.match_datetime.strftime("%H:%M")
        if match.match_datetime
        and (match.match_datetime.hour or match.match_datetime.minute)
        else None,
        "season": "2024-25",  # TODO: derive from match date
        "age_group": config.age_group,
        "match_type": "League",
        "division": division_name,
        "division_id": division_id,
        "league": config.league,
        # Convert non-integer scores (like "TBD") to None for RabbitMQ validation
        "home_score": match.home_score if isinstance(match.home_score, int) else None,
        "away_score": match.away_score if isinstance(match.away_score, int) else None,
        "match_status": match.match_status,
        "external_match_id": match.match_id,
        "location": match.location,
        "source": "match-scraper",
    }


def save_matches_to_file(
    matches: list[Match], file_path: str, age_group: str, division: str
) -> bool:
    """Save matches to JSON file for later processing."""
    try:
        # Convert matches to JSON-serializable format
        matches_data = []
        for match in matches:
            match_data = {
                "match_id": match.match_id,
                "match_datetime": match.match_datetime.isoformat(),
                "location": match.location,
                "competition": match.competition,
                "home_team": normalize_team_name_for_display(match.home_team),
                "away_team": normalize_team_name_for_display(match.away_team),
                "home_score": match.home_score,
                "away_score": match.away_score,
                "match_status": match.match_status,
            }
            matches_data.append(match_data)

        # Create output data with metadata
        output_data = {
            "metadata": {
                "age_group": age_group,
                "division": division,
                "scraped_at": date.today().isoformat(),
                "total_matches": len(matches),
            },
            "matches": matches_data,
        }

        # Save to file
        with open(file_path, "w") as f:
            json.dump(output_data, f, indent=2)

        return True

    except Exception as e:
        console.print(f"[red]❌ Failed to save matches to {file_path}: {e}[/red]")
        return False


async def run_scraper(
    config: ScrapingConfig,
    verbose: bool = False,
    headless: bool = True,
) -> list[Match]:
    """Run the scraper with progress indication.

    Returns:
        List of scraped Match objects
    """
    import logging
    import warnings

    # Suppress OpenTelemetry warnings and connection errors unless verbose
    if not verbose:
        # Suppress urllib3 connection warnings
        warnings.filterwarnings("ignore", message=".*Connection.*")
        warnings.filterwarnings("ignore", message=".*HTTPConnectionPool.*")

        # Suppress OpenTelemetry logging
        logging.getLogger("opentelemetry").setLevel(logging.CRITICAL)
        logging.getLogger("urllib3").setLevel(logging.CRITICAL)

    matches = []

    # Disable progress spinner in container environments (NO_COLOR=1)
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
        disable=not use_rich,  # Disable progress bar when NO_COLOR is set
    ) as progress:
        # Add scraping progress task
        scrape_task = progress.add_task("🌐 Initializing browser...", total=None)

        try:
            scraper = MLSScraper(config, headless=headless)

            progress.update(scrape_task, description="🔍 Scraping matches...")
            matches = await scraper.scrape_matches()

            progress.update(scrape_task, description="✅ Scraping completed!")
            progress.remove_task(scrape_task)

        except MLSScraperError as e:
            progress.update(scrape_task, description=f"❌ Scraping failed: {e}")
            raise
        except Exception as e:
            progress.update(scrape_task, description=f"💥 Unexpected error: {e}")
            raise

    return matches


@app.command()
def scrape(
    age_group: Annotated[
        str, typer.Option("--age-group", "-a", help="Age group to scrape")
    ] = DEFAULT_AGE_GROUP,
    league: Annotated[
        str,
        typer.Option(
            "--league",
            "-lg",
            help="League type: 'Homegrown' (default) or 'Academy'",
        ),
    ] = DEFAULT_LEAGUE,
    division: Annotated[
        str,
        typer.Option(
            "--division",
            "-d",
            help="Division to scrape (used with Homegrown league)",
        ),
    ] = DEFAULT_DIVISION,
    conference: Annotated[
        str,
        typer.Option(
            "--conference",
            help="Conference filter for Academy league (e.g., 'New England', 'Northeast')",
        ),
    ] = DEFAULT_CONFERENCE,
    start: Annotated[
        int,
        typer.Option(
            "--start",
            help="Days backward from today (0=today, 1=yesterday, 7=week ago)",
        ),
    ] = DEFAULT_START_OFFSET,
    end: Annotated[
        int,
        typer.Option(
            "--end",
            "-e",
            help="Days from today: positive=forward, negative=backward (2=tomorrow, -7=week ago)",
        ),
    ] = DEFAULT_END_OFFSET,
    from_date: Annotated[
        Optional[str],
        typer.Option(
            "--from", help="Absolute start date (YYYY-MM-DD format, e.g., 2025-09-05)"
        ),
    ] = None,
    to_date: Annotated[
        Optional[str],
        typer.Option(
            "--to", help="Absolute end date (YYYY-MM-DD format, e.g., 2025-09-08)"
        ),
    ] = None,
    club: Annotated[
        str, typer.Option("--club", "-c", help="Filter by specific club")
    ] = "",
    competition: Annotated[
        str,
        typer.Option("--competition", "-comp", help="Filter by specific competition"),
    ] = "",
    upcoming_only: Annotated[
        bool, typer.Option("--upcoming", "-u", help="Show only upcoming games")
    ] = False,
    stats: Annotated[
        bool, typer.Option("--stats", "-s", help="Show detailed statistics")
    ] = False,
    quiet: Annotated[
        bool, typer.Option("--quiet", "-q", help="Minimal output")
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose", "-v", help="Show detailed logs and full error traces"
        ),
    ] = False,
    limit: Annotated[
        int, typer.Option("--limit", "-l", help="Maximum number of matches to display")
    ] = 0,
    headless: Annotated[
        bool,
        typer.Option("--headless/--no-headless", help="Run browser in headless mode"),
    ] = True,
    save_file: Annotated[
        Optional[str],
        typer.Option(
            "--save", help="Save matches to JSON file (e.g., --save games.json)"
        ),
    ] = None,
    submit_queue: Annotated[
        bool,
        typer.Option(
            "--submit-queue/--no-submit-queue",
            help="Submit matches to RabbitMQ queue for processing (default: True)",
        ),
    ] = True,
    exchange_name: Annotated[
        Optional[str],
        typer.Option(
            "--exchange",
            help="RabbitMQ exchange to publish to (fanout to multiple queues). Default: matches-fanout",
        ),
    ] = None,
    queue_name: Annotated[
        Optional[str],
        typer.Option(
            "--queue",
            help="Specific queue to publish to (bypasses exchange). Use for targeting dev/prod directly",
        ),
    ] = None,
) -> None:
    """
    ⚽ Scrape MLS match data and display in beautiful format.

    This command scrapes match data from the MLS website and displays it
    in a nicely formatted table with colors and statistics. By default,
    searches from yesterday to tomorrow. Use --start and --end to customize
    the date range (0=today, -1=yesterday, 1=tomorrow, etc.).
    """
    setup_environment(verbose)

    # Validate inputs
    if age_group not in VALID_AGE_GROUPS:
        console.print(f"[red]❌ Invalid age group: {age_group}[/red]")
        console.print(f"Valid options: {', '.join(VALID_AGE_GROUPS)}")
        raise typer.Exit(1)

    if league not in VALID_LEAGUES:
        console.print(f"[red]❌ Invalid league: {league}[/red]")
        console.print(f"Valid options: {', '.join(VALID_LEAGUES)}")
        raise typer.Exit(1)

    # Validate league-specific parameters
    if league == "Homegrown":
        if division not in VALID_DIVISIONS:
            console.print(f"[red]❌ Invalid division: {division}[/red]")
            console.print(f"Valid options: {', '.join(VALID_DIVISIONS)}")
            raise typer.Exit(1)
        # Warn if conference is provided but league is Homegrown
        if conference and conference != DEFAULT_CONFERENCE:
            console.print(
                "[yellow]⚠️  --conference is only used with --league Academy. It will be ignored.[/yellow]"
            )
    elif league == "Academy":
        if conference not in VALID_CONFERENCES:
            console.print(f"[red]❌ Invalid conference: {conference}[/red]")
            console.print(f"Valid options: {', '.join(VALID_CONFERENCES)}")
            raise typer.Exit(1)
        # Warn if division is provided but league is Academy
        if division and division != DEFAULT_DIVISION:
            console.print(
                "[yellow]⚠️  --division is only used with --league Homegrown. It will be ignored.[/yellow]"
            )

    if not quiet:
        display_header()

    # Create configuration
    config = create_config(
        age_group,
        league,
        division,
        start,
        end,
        club,
        competition,
        conference,
        verbose,
        from_date,
        to_date,
    )

    if not quiet:
        display_config_summary(config)
        console.print()

    try:
        # Run scraper with execution time tracking
        import secrets
        from datetime import datetime

        from src.utils.metrics import get_metrics

        metrics = get_metrics()

        # Generate run ID for audit logging
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        run_id = f"{timestamp}-{secrets.token_hex(3)}"

        # Initialize audit logger
        run_metadata = RunMetadata(
            league=config.league,
            age_group=config.age_group,
            division=config.division or config.conference,
            date_range=f"{config.start_date} to {config.end_date}",
        )
        audit_logger = AuditLogger(run_id=run_id, run_metadata=run_metadata)
        audit_logger.log_run_started()

        with metrics.time_execution():
            matches = asyncio.run(run_scraper(config, verbose, headless))

        # Initialize match comparison for change detection
        comparison = MatchComparison(audit_logger.get_state_file_path())
        comparison.load_previous_state()

        # Track counts for summary
        discovered_count = 0
        updated_count = 0
        unchanged_count = 0
        queue_submitted_count = 0
        queue_failed_count = 0

        # Build match dicts and perform audit logging for ALL matches
        # This happens regardless of queue submission
        match_dicts = []
        if matches:
            for match in matches:
                match_dict = build_match_dict(match, config)

                # Compare match and log audit event
                status, changes = comparison.compare_match(match.match_id, match_dict)
                if status == "discovered":
                    audit_logger.log_match_discovered(match.match_id, match_dict)
                    discovered_count += 1
                elif status == "updated":
                    assert changes is not None
                    audit_logger.log_match_updated(match.match_id, match_dict, changes)
                    updated_count += 1
                else:  # unchanged
                    audit_logger.log_match_unchanged(match.match_id, match_dict)
                    unchanged_count += 1

                match_dicts.append(match_dict)

        # Submit to RabbitMQ queue if requested
        if submit_queue and match_dicts:
            from src.celery.queue_client import MatchQueueClient

            console.print("\n[cyan]📨 Submitting matches to RabbitMQ...[/cyan]")

            try:
                queue_client = MatchQueueClient(
                    exchange_name=exchange_name,
                    queue_name=queue_name,
                )

                # Check connection first
                if not queue_client.check_connection():
                    console.print(
                        "[red]❌ Cannot connect to RabbitMQ - matches not queued[/red]"
                    )
                else:
                    # Submit batch
                    task_ids = queue_client.submit_matches_batch(match_dicts)

                    # Log queue submission success for each match
                    for match_dict, task_id in zip(match_dicts, task_ids):
                        if task_id:
                            audit_logger.log_queue_submitted(
                                match_dict["external_match_id"], task_id
                            )
                            queue_submitted_count += 1
                        else:
                            audit_logger.log_queue_failed(
                                match_dict["external_match_id"], "No task ID returned"
                            )
                            queue_failed_count += 1

                    console.print(
                        f"[green]✅ {len(task_ids)} matches queued for processing[/green]"
                    )

            except Exception as e:
                console.print(f"[red]❌ Queue submission failed: {e}[/red]")
                # Log queue failures for all matches
                for match_dict in match_dicts:
                    audit_logger.log_queue_failed(
                        match_dict["external_match_id"], str(e)
                    )
                    queue_failed_count += 1
                if verbose:
                    console.print_exception()

        # Save current state
        if match_dicts:
            state = comparison.build_state_from_matches(match_dicts)
            comparison.save_current_state(run_id, state)

        # Log run completion
        run_metadata.total_matches = len(matches) if matches else 0
        summary = RunSummary(
            total_matches=len(matches) if matches else 0,
            discovered=discovered_count,
            updated=updated_count,
            unchanged=unchanged_count,
            queue_submitted=queue_submitted_count,
            queue_failed=queue_failed_count,
        )
        audit_logger.log_run_completed(summary)

        # Filter for upcoming only if requested
        if upcoming_only:
            matches = [m for m in matches if m.match_status == "scheduled"]

        # Track original count before limiting
        original_count = len(matches)

        # Apply limit (sort by date first to get most relevant matches)
        if matches:
            matches.sort(
                key=lambda m: m.match_datetime if m.match_datetime else date.min
            )
            if limit > 0:
                matches = matches[:limit]

        if quiet:
            # Minimal output for scripting
            for match in matches:
                status = (
                    "✅"
                    if match.match_status == "completed"
                    else "⏰"
                    if match.match_status == "scheduled"
                    else "⏳"
                    if match.match_status == "tbd"
                    else "🔄"
                )
                score = f" ({match.get_score_string()})" if match.has_score() else ""
                date_str = (
                    match.match_datetime.strftime("%m/%d")
                    if match.match_datetime
                    else "TBD"
                )
                print(
                    f"{status} {date_str} {normalize_team_name_for_display(match.home_team)} vs {normalize_team_name_for_display(match.away_team)}{score}"
                )
            return  # Exit early for quiet mode
        else:
            # Rich output
            display_matches_table(matches)

            if stats:
                console.print()
                display_statistics(matches)

            if not upcoming_only and matches:
                display_upcoming_games(matches)

        # Success message
        if not quiet:
            if original_count > len(matches):
                console.print(
                    f"\n[green]✅ Showing {len(matches)} of {original_count} matches found![/green]"
                )
            else:
                console.print(
                    f"\n[green]✅ Successfully found {len(matches)} matches![/green]"
                )

            # Save matches to file if requested
            if save_file and matches:
                if save_matches_to_file(matches, save_file, age_group, division):
                    console.print(
                        f"[green]💾 Saved {len(matches)} matches to {save_file}[/green]"
                    )

    except MLSScraperError as e:
        console.print(f"[red]❌ Scraping failed: {e}[/red]")
        if verbose:
            console.print_exception()
        raise typer.Exit(1) from e
    except Exception as e:
        handle_cli_error(e, verbose)
        raise typer.Exit(1) from e


@app.command()
def upcoming(
    age_group: Annotated[
        str, typer.Option("--age-group", "-a", help="Age group to scrape")
    ] = DEFAULT_AGE_GROUP,
    division: Annotated[
        str, typer.Option("--division", "-d", help="Division to scrape")
    ] = DEFAULT_DIVISION,
    days: Annotated[
        int, typer.Option("--days", "-n", help="Number of days to look ahead")
    ] = DEFAULT_DAYS,
    limit: Annotated[
        int, typer.Option("--limit", "-l", help="Maximum number of games to show")
    ] = 10,
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose", "-v", help="Show detailed logs and full error traces"
        ),
    ] = False,
) -> None:
    """
    🔮 Show upcoming games in a clean, focused format.

    Perfect for quickly checking what games are coming up.
    """
    setup_environment(verbose)

    console.print("[bold cyan]⚽ Upcoming MLS Games[/bold cyan]\n")

    # Create configuration for future games
    config = create_config(
        age_group,
        league="Homegrown",
        division=division,
        start_offset=0,
        end_offset=days,
        verbose=verbose,
    )

    try:
        matches = asyncio.run(run_scraper(config, verbose))
        upcoming_matches = [m for m in matches if m.match_status == "scheduled"]

        if not upcoming_matches:
            console.print(
                f"[yellow]No upcoming games found in the next {days} days.[/yellow]"
            )
            return

        # Sort by date
        upcoming_matches.sort(
            key=lambda m: m.match_datetime if m.match_datetime else date.max
        )

        for i, match in enumerate(upcoming_matches[:limit], 1):
            match_date = (
                match.match_datetime.strftime("%a %m/%d")
                if match.match_datetime
                else "TBD"
            )
            # Extract time from datetime
            try:
                match_time = (
                    match.match_datetime.strftime("%I:%M %p")
                    if match.match_datetime
                    else "TBD"
                )
            except (AttributeError, ValueError):
                match_time = "TBD"

            console.print(
                f"[bold cyan]{i:2d}.[/bold cyan] [green]{normalize_team_name_for_display(match.home_team)}[/green] vs [red]{normalize_team_name_for_display(match.away_team)}[/red]"
            )
            console.print(f"     📅 {match_date} at {match_time}")
            if match.location:
                console.print(f"     🏟️  {match.location}")
            console.print()

    except Exception as e:
        handle_cli_error(e, verbose)
        raise typer.Exit(1) from e


@app.command()
def interactive(
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose", "-v", help="Show detailed logs and full error traces"
        ),
    ] = False,
) -> None:
    """
    🎮 Interactive mode for exploring MLS match data.

    Provides a guided experience for configuring and running scrapes.
    """
    setup_environment(verbose)
    display_header()

    console.print("[bold]Welcome to interactive mode![/bold] 🎮\n")

    # Get configuration from user
    console.print("Let's configure your search:")

    # Age group selection
    console.print(f"\nAvailable age groups: {', '.join(VALID_AGE_GROUPS)}")
    age_group = Prompt.ask(
        "Age group", default=DEFAULT_AGE_GROUP, choices=VALID_AGE_GROUPS
    )

    # Division selection
    console.print(f"\nAvailable divisions: {', '.join(VALID_DIVISIONS)}")
    division = Prompt.ask("Division", default=DEFAULT_DIVISION, choices=VALID_DIVISIONS)

    # Date range selection
    start_offset = int(
        Prompt.ask("Start date offset from today (0=today, -1=yesterday)", default="-1")
    )
    end_offset = int(
        Prompt.ask(
            "End date offset from today (0=today, 1=tomorrow, 7=week from now)",
            default="1",
        )
    )

    # Optional filters
    club = Prompt.ask("Club filter (optional)", default="")
    competition = Prompt.ask("Competition filter (optional)", default="")

    # Show statistics?
    show_stats = Confirm.ask("Show detailed statistics?", default=True)

    console.print("\n" + "=" * 50)

    # Create and display configuration
    config = create_config(
        age_group,
        league="Homegrown",
        division=division,
        start_offset=start_offset,
        end_offset=end_offset,
        club=club,
        competition=competition,
        verbose=False,
    )
    display_config_summary(config)

    if not Confirm.ask("\nProceed with scraping?", default=True):
        console.print("Cancelled.")
        return

    try:
        matches = asyncio.run(run_scraper(config, verbose))

        console.print()
        display_matches_table(matches)

        if show_stats and matches:
            console.print()
            display_statistics(matches)

        if matches:
            display_upcoming_games(matches)

        console.print(f"\n[green]✅ Found {len(matches)} matches![/green]")

    except Exception as e:
        handle_cli_error(e, verbose)


@app.command()
def test_quiet() -> None:
    """
    🔇 Test quiet mode output with sample data.

    Shows how quiet mode looks for scripting purposes.
    """

    # Create sample matches
    sample_matches = [
        Match(
            match_id="demo_1",
            home_team="FC Dallas Youth",
            away_team="Houston Dynamo Academy",
            match_datetime=datetime(2025, 9, 20, 15, 0),
            location="Toyota Stadium",
            competition="MLS Next",
            home_score=None,
            away_score=None,
        ),
        Match(
            match_id="demo_2",
            home_team="Austin FC Academy",
            away_team="San Antonio FC Youth",
            match_datetime=datetime(2025, 9, 18, 10, 0),
            location="St. David's Performance Center",
            competition="MLS Next",
            home_score=2,
            away_score=1,
        ),
    ]

    console.print("[bold]Quiet mode output (for scripting):[/bold]")
    console.print("[dim]" + "=" * 50 + "[/dim]")

    # Simulate quiet mode output
    for match in sample_matches:
        status = (
            "✅"
            if match.match_status == "completed"
            else "⏰"
            if match.match_status == "scheduled"
            else "⏳"
            if match.match_status == "tbd"
            else "🔄"
        )
        score = f" ({match.get_score_string()})" if match.has_score() else ""
        date_str = (
            match.match_datetime.strftime("%m/%d") if match.match_datetime else "TBD"
        )
        console.print(
            f"{status} {date_str} {normalize_team_name_for_display(match.home_team)} vs {normalize_team_name_for_display(match.away_team)}{score}",
            style="white",
        )

    console.print("[dim]" + "=" * 50 + "[/dim]")
    console.print("[dim]Perfect for piping to other commands or scripts![/dim]")


@app.command()
def demo() -> None:
    """
    🎭 Demo mode with sample data to test the CLI interface.

    Shows how the CLI looks with sample match data without scraping.
    """

    display_header()

    # Create sample matches
    sample_matches = [
        Match(
            match_id="demo_1",
            home_team="FC Dallas Youth",
            away_team="Houston Dynamo Academy",
            match_datetime=datetime(2025, 9, 20, 15, 0),
            location="Toyota Stadium",
            competition="MLS Next",
            home_score=None,
            away_score=None,
        ),
        Match(
            match_id="demo_2",
            home_team="Austin FC Academy",
            away_team="San Antonio FC Youth",
            match_datetime=datetime(2025, 9, 18, 10, 0),
            location="St. David's Performance Center",
            competition="MLS Next",
            home_score=2,
            away_score=1,
        ),
        Match(
            match_id="demo_3",
            home_team="Real Salt Lake Academy",
            away_team="Colorado Rapids Youth",
            match_datetime=datetime(2025, 9, 19, 13, 30),
            location="Zions Bank Training Center",
            competition="MLS Next",
            home_score=1,
            away_score=0,
        ),
    ]

    console.print("[bold yellow]🎭 Demo Mode - Sample Data[/bold yellow]\n")

    # Show sample configuration
    config_table = Table(show_header=False, box=None, padding=(0, 1))
    config_table.add_column("Setting", style="cyan")
    config_table.add_column("Value", style="white")

    config_table.add_row("Age Group", "U14")
    config_table.add_row("Division", "Southwest")
    config_table.add_row("Date Range", "2025-09-12 to 2025-09-19")
    config_table.add_row("Club Filter", "All clubs")
    config_table.add_row("Competition Filter", "All competitions")

    console.print(Panel(config_table, title="📋 Configuration", border_style="cyan"))
    console.print()

    # Display matches
    display_matches_table(sample_matches)
    console.print()

    # Display statistics
    display_statistics(sample_matches)

    # Display upcoming games
    display_upcoming_games(sample_matches)

    console.print(
        "\n[green]✅ Demo completed! This is how real data would look.[/green]"
    )


@app.command()
def debug(
    step: Annotated[
        str,
        typer.Option(
            "--step",
            "-s",
            help="Debug step: url, browser, navigate, consent, filters, extract, inspect",
        ),
    ] = "all",
    headless: Annotated[
        bool,
        typer.Option("--headless/--no-headless", help="Run browser in headless mode"),
    ] = False,
    timeout: Annotated[
        int, typer.Option("--timeout", "-t", help="Browser timeout in seconds")
    ] = 60,
) -> None:
    """
    🐛 Debug the MLS scraper step by step.

    This command helps diagnose issues with the scraping process by running
    individual steps and showing detailed information.
    """
    setup_environment(verbose=True)  # Always verbose for debugging

    console.print("[bold red]🐛 MLS Scraper Debug Mode[/bold red]\n")

    if step == "url" or step == "all":
        console.print("[bold cyan]Step 1: Testing URL accessibility[/bold cyan]")
        test_url_accessibility()
        console.print()

    if step == "browser" or step == "all":
        console.print("[bold cyan]Step 2: Testing browser initialization[/bold cyan]")
        asyncio.run(test_browser_init(headless, timeout))
        console.print()

    if step == "navigate" or step == "all":
        console.print("[bold cyan]Step 3: Testing navigation[/bold cyan]")
        asyncio.run(test_navigation(headless, timeout))
        console.print()

    if step == "consent" or step == "all":
        console.print("[bold cyan]Step 3.5: Testing consent handling[/bold cyan]")
        asyncio.run(test_consent_handling(headless, timeout))
        console.print()

    if step == "filters" or step == "all":
        console.print("[bold cyan]Step 4: Testing filter application[/bold cyan]")
        asyncio.run(test_filters(headless, timeout))
        console.print()

    if step == "extract" or step == "all":
        console.print("[bold cyan]Step 5: Testing match extraction[/bold cyan]")
        asyncio.run(test_extraction(headless, timeout))
        console.print()

    if step == "inspect" or step == "all":
        console.print("[bold cyan]Step 6: Inspecting page elements[/bold cyan]")
        asyncio.run(test_page_inspection(headless, timeout))
        console.print()

    console.print("[green]✅ Debug session completed![/green]")


def test_url_accessibility() -> None:
    """Test if the MLS URL is accessible via HTTP."""
    import requests

    url = "https://www.mlssoccer.com/mlsnext/schedule/all/"

    try:
        console.print(f"   🌐 Testing URL: {url}")

        response = requests.get(
            url,
            timeout=10,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            },
        )

        console.print(f"   ✅ Status Code: {response.status_code}")
        console.print(f"   📏 Content Length: {len(response.content)} bytes")
        console.print(f"   🕒 Response Time: {response.elapsed.total_seconds():.2f}s")

        if response.status_code == 200:
            console.print("   ✅ URL is accessible via HTTP")
        else:
            console.print(
                f"   ⚠️  HTTP status indicates potential issue: {response.status_code}"
            )

    except requests.exceptions.Timeout:
        console.print("   ❌ HTTP request timed out - network or server issue")
    except requests.exceptions.ConnectionError:
        console.print("   ❌ Connection error - check internet connection")
    except Exception as e:
        console.print(f"   ❌ HTTP test failed: {e}")


async def test_browser_init(headless: bool, timeout: int) -> None:
    """Test browser initialization."""
    from src.scraper.browser import BrowserConfig, BrowserManager

    try:
        console.print(
            f"   🚀 Initializing browser (headless={headless}, timeout={timeout}s)"
        )

        config = BrowserConfig(
            headless=headless,
            timeout=timeout * 1000,  # Convert to milliseconds
        )

        browser_manager = BrowserManager(config)
        await browser_manager.initialize()

        console.print("   ✅ Browser initialized successfully")

        # Test page creation
        async with browser_manager.get_page() as page:
            console.print("   ✅ Page created successfully")
            viewport = page.viewport_size
            console.print(f"   📱 Viewport: {viewport}")

        await browser_manager.cleanup()
        console.print("   ✅ Browser cleanup completed")

    except Exception as e:
        console.print(f"   ❌ Browser initialization failed: {e}")
        console.print("   💡 Try: uv run playwright install")


async def test_navigation(headless: bool, timeout: int) -> None:
    """Test navigation to MLS website."""
    from src.scraper.browser import BrowserConfig, BrowserManager, PageNavigator

    url = "https://www.mlssoccer.com/mlsnext/schedule/all/"

    try:
        console.print(f"   🌐 Navigating to: {url}")

        config = BrowserConfig(headless=headless, timeout=timeout * 1000)
        browser_manager = BrowserManager(config)
        await browser_manager.initialize()

        async with browser_manager.get_page() as page:
            navigator = PageNavigator(page, max_retries=1)

            # Try different wait strategies
            wait_strategies: list[
                Literal["load", "domcontentloaded", "networkidle"]
            ] = ["load", "domcontentloaded", "networkidle"]

            for strategy in wait_strategies:
                console.print(f"   🔄 Trying wait strategy: {strategy}")

                success = await navigator.navigate_to(url, wait_until=strategy)

                if success:
                    console.print(
                        f"   ✅ Navigation successful with '{strategy}' strategy"
                    )
                    console.print(f"   📄 Page title: {await page.title()}")
                    console.print(f"   🔗 Current URL: {page.url}")
                    break
                else:
                    console.print(f"   ❌ Navigation failed with '{strategy}' strategy")
            else:
                console.print("   ❌ All navigation strategies failed")

        await browser_manager.cleanup()

    except Exception as e:
        console.print(f"   ❌ Navigation test failed: {e}")


async def test_consent_handling(headless: bool, timeout: int) -> None:
    """Test cookie consent handling."""
    from src.scraper.browser import BrowserConfig, BrowserManager, PageNavigator
    from src.scraper.consent_handler import MLSConsentHandler

    url = "https://www.mlssoccer.com/mlsnext/schedule/all/"

    try:
        console.print(f"   🍪 Testing consent handling on: {url}")

        config = BrowserConfig(headless=headless, timeout=timeout * 1000)
        browser_manager = BrowserManager(config)
        await browser_manager.initialize()

        async with browser_manager.get_page() as page:
            # Navigate first
            navigator = PageNavigator(page, max_retries=1)
            success = await navigator.navigate_to(url, wait_until="load")

            if not success:
                console.print("   ❌ Cannot test consent - navigation failed")
                return

            console.print("   ✅ Page loaded, checking for consent banner...")

            # Test consent handling
            consent_handler = MLSConsentHandler(page)

            # Check if banner is present
            banner_present = await consent_handler.interactor.wait_for_element(
                consent_handler.ONETRUST_BANNER_SELECTOR, timeout=3000
            )

            if banner_present:
                console.print("   🎯 OneTrust consent banner detected")

                # Handle consent
                consent_handled = await consent_handler.handle_consent_banner()

                if consent_handled:
                    console.print("   ✅ Consent banner handled successfully")

                    # Wait for page to be ready
                    page_ready = await consent_handler.wait_for_page_ready()
                    if page_ready:
                        console.print("   ✅ Page is ready after consent handling")
                    else:
                        console.print("   ⚠️  Page readiness uncertain")
                else:
                    console.print("   ❌ Consent handling failed")
            else:
                console.print(
                    "   ℹ️  No consent banner detected (may have been handled already)"
                )

        await browser_manager.cleanup()

    except Exception as e:
        console.print(f"   ❌ Consent test failed: {e}")


async def test_filters(headless: bool, timeout: int) -> None:
    """Test filter application."""
    from datetime import date, timedelta

    from src.scraper.browser import BrowserConfig, BrowserManager, PageNavigator
    from src.scraper.config import ScrapingConfig
    from src.scraper.filter_application import MLSFilterApplicator

    try:
        console.print("   🎯 Testing filter discovery and application")

        config = BrowserConfig(headless=headless, timeout=timeout * 1000)
        browser_manager = BrowserManager(config)
        await browser_manager.initialize()

        # Create scraping config
        scraping_config = ScrapingConfig(
            age_group="U14",
            club="",
            competition="",
            division="Northeast",
            look_back_days=7,
            start_date=date.today() - timedelta(days=7),
            end_date=date.today(),
            missing_table_api_url="https://api.missing-table.com",
            missing_table_api_key="test-key",
            log_level="DEBUG",
        )

        async with browser_manager.get_page() as page:
            # Navigate first
            navigator = PageNavigator(page, max_retries=1)
            success = await navigator.navigate_to(
                "https://www.mlssoccer.com/mlsnext/schedule/all/", wait_until="load"
            )

            if not success:
                console.print("   ❌ Cannot test filters - navigation failed")
                return

            # Handle consent banner
            console.print("   🍪 Handling cookie consent...")
            from src.scraper.consent_handler import MLSConsentHandler

            consent_handler = MLSConsentHandler(page)
            consent_handled = await consent_handler.handle_consent_banner()

            if consent_handled:
                console.print("   ✅ Consent handled successfully")
                await consent_handler.wait_for_page_ready()
            else:
                console.print("   ⚠️  Consent handling failed, continuing anyway")

            # Test filter discovery
            filter_applicator = MLSFilterApplicator(page)
            options = await filter_applicator.discover_available_options()

            console.print("   📋 Discovered filter options:")
            for filter_type, values in options.items():
                console.print(f"      {filter_type}: {len(values)} options")
                if values:
                    console.print(f"         Sample: {list(values)[:3]}")

            # Test filter application
            if options:
                console.print("   🎯 Testing filter application...")
                success = await filter_applicator.apply_all_filters(scraping_config)
                if success:
                    console.print("   ✅ Filters applied successfully")
                else:
                    console.print("   ❌ Filter application failed")
            else:
                console.print(
                    "   ⚠️  No filter options discovered - page structure may have changed"
                )

        await browser_manager.cleanup()

    except Exception as e:
        console.print(f"   ❌ Filter test failed: {e}")


async def test_extraction(headless: bool, timeout: int) -> None:
    """Test match extraction."""
    from src.scraper.browser import BrowserConfig, BrowserManager, PageNavigator
    from src.scraper.match_extraction import MLSMatchExtractor

    try:
        console.print("   ⚽ Testing match extraction")

        config = BrowserConfig(headless=headless, timeout=timeout * 1000)
        browser_manager = BrowserManager(config)
        await browser_manager.initialize()

        async with browser_manager.get_page() as page:
            # Navigate first
            navigator = PageNavigator(page, max_retries=1)
            success = await navigator.navigate_to(
                "https://www.mlssoccer.com/mlsnext/schedule/all/", wait_until="load"
            )

            if not success:
                console.print("   ❌ Cannot test extraction - navigation failed")
                return

            # Handle consent banner
            console.print("   🍪 Handling cookie consent...")
            from src.scraper.consent_handler import MLSConsentHandler

            consent_handler = MLSConsentHandler(page)
            await consent_handler.handle_consent_banner()
            await consent_handler.wait_for_page_ready()

            # Test match extraction
            extractor = MLSMatchExtractor(page)
            matches = await extractor.extract_matches("U14", "Northeast")

            console.print("   📊 Extraction results:")
            console.print(f"      Matches found: {len(matches)}")

            if matches:
                console.print(
                    f"      Sample match: {normalize_team_name_for_display(matches[0].home_team)} vs {normalize_team_name_for_display(matches[0].away_team)}"
                )
                console.print(f"      Match status: {matches[0].match_status}")
            else:
                console.print("      ⚠️  No matches extracted - check page structure")

        await browser_manager.cleanup()

    except Exception as e:
        console.print(f"   ❌ Extraction test failed: {e}")


async def test_page_inspection(headless: bool, timeout: int) -> None:
    """Inspect page elements to understand the structure."""
    from src.scraper.browser import BrowserConfig, BrowserManager, PageNavigator
    from src.scraper.consent_handler import MLSConsentHandler

    url = "https://www.mlssoccer.com/mlsnext/schedule/all/"

    try:
        console.print(f"   🔍 Inspecting page elements on: {url}")

        config = BrowserConfig(headless=headless, timeout=timeout * 1000)
        browser_manager = BrowserManager(config)
        await browser_manager.initialize()

        async with browser_manager.get_page() as page:
            # Navigate and handle consent
            navigator = PageNavigator(page, max_retries=1)
            success = await navigator.navigate_to(url, wait_until="load")

            if not success:
                console.print("   ❌ Cannot inspect - navigation failed")
                return

            # Handle consent
            consent_handler = MLSConsentHandler(page)
            await consent_handler.handle_consent_banner()
            await consent_handler.wait_for_page_ready()

            console.print("   🔍 Inspecting page structure...")

            # Get page title
            title = await page.title()
            console.print(f"   📄 Page title: {title}")

            # Check for common form elements
            console.print("   🔍 Looking for form elements...")

            # Check for select elements
            selects = await page.query_selector_all("select")
            console.print(f"   📋 Found {len(selects)} select elements")

            for i, select in enumerate(selects[:5]):  # Show first 5
                name = await select.get_attribute("name") or "no-name"
                id_attr = await select.get_attribute("id") or "no-id"
                classes = await select.get_attribute("class") or "no-class"
                console.print(
                    f"      {i + 1}. name='{name}' id='{id_attr}' class='{classes}'"
                )

            # Check for input elements
            inputs = await page.query_selector_all("input")
            console.print(f"   📝 Found {len(inputs)} input elements")

            # Check for buttons
            buttons = await page.query_selector_all("button")
            console.print(f"   🔘 Found {len(buttons)} button elements")

            # Look for filter-related text
            console.print("   🔍 Looking for filter-related content...")

            filter_keywords = ["age", "division", "club", "competition", "filter"]
            for keyword in filter_keywords:
                elements = await page.query_selector_all(f"*:has-text('{keyword}')")
                if elements:
                    console.print(
                        f"      Found {len(elements)} elements containing '{keyword}'"
                    )

            # Check if page is still loading
            console.print("   ⏳ Checking if page is still loading...")

            loading_indicators = await page.query_selector_all(
                ".loading, .spinner, [data-loading]"
            )
            if loading_indicators:
                console.print(
                    f"      ⚠️  Found {len(loading_indicators)} loading indicators - page may still be loading"
                )
            else:
                console.print("      ✅ No loading indicators found")

            # Get page URL to see if there were redirects
            current_url = page.url
            console.print(f"   🔗 Current URL: {current_url}")

            # Wait a bit longer and check again
            console.print("   ⏳ Waiting 5 seconds for dynamic content...")
            await asyncio.sleep(5)

            # Check selects again
            selects_after = await page.query_selector_all("select")
            console.print(
                f"   📋 After waiting: Found {len(selects_after)} select elements"
            )

            if len(selects_after) > len(selects):
                console.print("      ✅ More selects appeared after waiting!")

        await browser_manager.cleanup()

    except Exception as e:
        console.print(f"   ❌ Page inspection failed: {e}")


@app.command()
def inspect(
    headless: Annotated[
        bool,
        typer.Option("--headless/--no-headless", help="Run browser in headless mode"),
    ] = False,
    timeout: Annotated[
        int, typer.Option("--timeout", "-t", help="Browser timeout in seconds")
    ] = 120,
) -> None:
    """
    🔍 Open browser and navigate to MLS page for manual inspection.

    This command opens the browser, navigates to the MLS page, and keeps it open
    so you can manually inspect for pop-ups, overlays, or other blocking elements.
    """
    setup_environment(verbose=True)

    console.print("[bold blue]🔍 Browser Inspector Mode[/bold blue]\n")
    console.print("Opening browser and navigating to MLS Next page...")
    console.print("The browser will stay open for manual inspection.")
    console.print("Press Ctrl+C when you're done inspecting.\n")

    asyncio.run(inspect_browser(headless, timeout))


async def inspect_browser(headless: bool, timeout: int) -> None:
    """Open browser and keep it open for manual inspection."""
    from src.scraper.browser import BrowserConfig, BrowserManager, PageNavigator

    url = "https://www.mlssoccer.com/mlsnext/schedule/all/"

    try:
        console.print(f"🚀 Initializing browser (headless={headless})")

        config = BrowserConfig(
            headless=headless,
            timeout=timeout * 1000,  # Convert to milliseconds
        )

        browser_manager = BrowserManager(config)
        await browser_manager.initialize()

        console.print("✅ Browser initialized")

        async with browser_manager.get_page() as page:
            console.print(f"🌐 Navigating to: {url}")

            navigator = PageNavigator(page, max_retries=1)
            success = await navigator.navigate_to(url, wait_until="load")

            if success:
                console.print("✅ Navigation successful!")
                console.print(f"📄 Page title: {await page.title()}")
                console.print(f"🔗 Current URL: {page.url}")

                # Wait a bit for any dynamic content to load
                console.print("⏳ Waiting 3 seconds for dynamic content...")
                await asyncio.sleep(3)

                # Check for common pop-up/overlay selectors
                console.print("\n🔍 Checking for common pop-ups and overlays...")

                popup_selectors = [
                    # Common modal/popup selectors
                    ".modal",
                    ".popup",
                    ".overlay",
                    ".dialog",
                    "[role='dialog']",
                    "[role='alertdialog']",
                    ".cookie-banner",
                    ".cookie-notice",
                    ".gdpr-notice",
                    ".newsletter-popup",
                    ".subscription-modal",
                    ".age-gate",
                    ".location-selector",
                    # Bootstrap modals
                    ".modal.show",
                    ".modal.fade.show",
                    # Common close button patterns
                    ".close",
                    ".modal-close",
                    "[aria-label*='close' i]",
                    "button[data-dismiss='modal']",
                    # MLS specific
                    ".mls-modal",
                    ".mls-popup",
                    ".mls-overlay",
                ]

                found_popups = []
                for selector in popup_selectors:
                    try:
                        elements = await page.query_selector_all(selector)
                        if elements:
                            for element in elements:
                                is_visible = await element.is_visible()
                                if is_visible:
                                    text_content = await element.text_content()
                                    found_popups.append(
                                        {
                                            "selector": selector,
                                            "text": text_content[:100]
                                            if text_content
                                            else "No text",
                                            "element": element,
                                        }
                                    )
                    except Exception:
                        continue

                if found_popups:
                    console.print(
                        f"⚠️  Found {len(found_popups)} visible pop-up/overlay elements:"
                    )
                    for i, popup in enumerate(found_popups, 1):
                        console.print(f"   {i}. Selector: {popup['selector']}")
                        console.print(f"      Text: {popup['text']}")
                        console.print()
                else:
                    console.print("✅ No obvious pop-ups or overlays detected")

                # Check page readiness
                console.print("📊 Page readiness check:")
                ready_state = await page.evaluate("document.readyState")
                console.print(f"   Document ready state: {ready_state}")

                # Check for loading indicators
                loading_selectors = [
                    ".loading",
                    ".spinner",
                    "[data-loading='true']",
                    ".loader",
                ]
                loading_elements = []
                for selector in loading_selectors:
                    elements = await page.query_selector_all(selector)
                    for element in elements:
                        if await element.is_visible():
                            loading_elements.append(selector)

                if loading_elements:
                    console.print(f"   ⏳ Loading indicators found: {loading_elements}")
                else:
                    console.print("   ✅ No loading indicators visible")

                console.print("\n🎯 Browser is ready for inspection!")
                console.print("The browser window should be open now.")
                console.print("Look for:")
                console.print("  • Pop-up windows or modal dialogs")
                console.print("  • Cookie consent banners")
                console.print("  • Age verification gates")
                console.print("  • Newsletter signup overlays")
                console.print("  • Location selection prompts")
                console.print("  • Any blocking elements")
                console.print("\nPress Ctrl+C when done inspecting...")

                # Keep the browser open until user interrupts
                try:
                    while True:
                        await asyncio.sleep(1)
                except KeyboardInterrupt:
                    console.print("\n👋 Closing browser...")

            else:
                console.print("❌ Navigation failed")

        await browser_manager.cleanup()
        console.print("✅ Browser closed")

    except KeyboardInterrupt:
        console.print("\n👋 Inspection interrupted by user")
    except Exception as e:
        console.print(f"❌ Error during inspection: {e}")


# Create config subcommand group
config_app = typer.Typer(name="config", help="⚙️ Configuration management")
app.add_typer(config_app, name="config")

# Import and add audit commands
from src.cli.audit_commands import app as audit_app  # noqa: E402

app.add_typer(audit_app, name="audit")


@config_app.command("show")
def config_show() -> None:
    """
    📋 Show current environment configuration.

    Displays the current values of all environment variables used by the scraper.
    """
    display_header()
    display_current_config()


@config_app.command("setup")
def config_setup() -> None:
    """
    🚀 Interactive setup of environment variables.

    Guides you through setting up all required and optional environment variables.
    """
    display_header()
    interactive_setup()


@config_app.command("set")
def config_set(
    variable: Annotated[str, typer.Argument(help="Environment variable name")],
    value: Annotated[str, typer.Argument(help="Environment variable value")],
) -> None:
    """
    📝 Set a specific environment variable.

    Sets the value of a specific environment variable and saves it to .env file.
    """
    if set_variable(variable, value):
        console.print(f"[green]✅ Successfully set {variable}[/green]")
    else:
        raise typer.Exit(1)


@config_app.command("validate")
def config_validate() -> None:
    """
    ✅ Validate current configuration.

    Checks if all required environment variables are properly configured.
    """
    if validate_config():
        console.print("\n[green]🎉 Configuration is valid and ready to use![/green]")
    else:
        console.print(
            "\n[yellow]💡 Run 'mls-scraper config setup' to fix configuration issues.[/yellow]"
        )
        raise typer.Exit(1)


@config_app.command("options")
def config_options() -> None:
    """
    🎯 Show available CLI options and examples.

    Displays available age groups, divisions, and usage examples.
    """
    display_header()

    # Age groups
    age_table = Table(title="🎯 Available Age Groups", show_header=False)
    age_table.add_column("Age Group", style="cyan")
    age_table.add_column("Description", style="white")

    for age in VALID_AGE_GROUPS:
        age_table.add_row(age, f"Under {age[1:]} years old")

    console.print(age_table)
    console.print()

    # Divisions
    div_table = Table(title="🗺️  Available Divisions", show_header=False)
    div_table.add_column("Division", style="green")

    for i in range(0, len(VALID_DIVISIONS), 3):
        row = VALID_DIVISIONS[i : i + 3]
        div_table.add_row(*row)

    console.print(div_table)
    console.print()

    # Examples
    examples = [
        ("Show all matches (yesterday to tomorrow)", "mls-scraper scrape"),
        ("Show today's matches only", "mls-scraper scrape --start 0 --end 0"),
        ("Show next week (today to 7 days)", "mls-scraper scrape --start 0 --end 7"),
        ("Show last 3 days to today", "mls-scraper scrape --start -3 --end 0"),
        ("Limit to 5 matches", "mls-scraper scrape -l 5"),
        ("Specific age/division", "mls-scraper scrape -a U16 -d Southwest"),
        ("Upcoming games only", "mls-scraper scrape --upcoming"),
        ("Quick upcoming check", "mls-scraper upcoming"),
        ("Interactive mode", "mls-scraper interactive"),
        ("Quiet output for scripts", "mls-scraper scrape --quiet"),
    ]

    example_table = Table(title="💡 Usage Examples", show_header=True)
    example_table.add_column("Description", style="cyan")
    example_table.add_column("Command", style="green")

    for desc, cmd in examples:
        example_table.add_row(desc, cmd)

    console.print(example_table)


# Backward compatibility - keep the old config command as an alias
@app.command("options")
def options() -> None:
    """
    🎯 Show available CLI options and examples (alias for 'config options').

    Displays available age groups, divisions, and usage examples.
    """
    config_options()


@app.command()
def discover(
    division: Annotated[
        str,
        typer.Option(
            "--division",
            "-d",
            help="Division to discover teams for",
        ),
    ],
    output: Annotated[
        str,
        typer.Option(
            "--output",
            "-o",
            help="Output JSON file path (default: <division>-clubs.json)",
        ),
    ] = "",
    league: Annotated[
        str,
        typer.Option("--league", "-lg", help="League type"),
    ] = DEFAULT_LEAGUE,
    headless: Annotated[
        bool,
        typer.Option("--headless/--no-headless", help="Run browser in headless mode"),
    ] = True,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Verbose output with debug info"),
    ] = False,
    age_groups: Annotated[
        Optional[str],
        typer.Option(
            "--age-groups",
            help="Comma-separated age groups to scan (default: U13,U14,U15,U16,U17,U19)",
        ),
    ] = None,
) -> None:
    """
    Discover clubs/teams in a division by scraping match data across age groups.

    Outputs a clubs.json-compatible JSON file listing every team found,
    along with the age groups each team appears in.

    Example:
        mls-scraper discover --division Florida
        mls-scraper discover --division Florida --output florida-clubs.json
        mls-scraper discover --division Florida --age-groups U14,U15
    """
    from src.scraper.division_discovery import DivisionDiscoverer

    setup_environment(verbose)

    # Validate division
    if division not in VALID_DIVISIONS:
        console.print(
            f"[red]Invalid division: {division}[/red]\n"
            f"[dim]Valid divisions: {', '.join(VALID_DIVISIONS)}[/dim]"
        )
        raise typer.Exit(code=1)

    # Validate league
    if league not in VALID_LEAGUES:
        console.print(
            f"[red]Invalid league: {league}[/red]\n"
            f"[dim]Valid leagues: {', '.join(VALID_LEAGUES)}[/dim]"
        )
        raise typer.Exit(code=1)

    # Parse age groups
    parsed_age_groups = None
    if age_groups:
        parsed_age_groups = [ag.strip() for ag in age_groups.split(",")]
        for ag in parsed_age_groups:
            if ag not in VALID_AGE_GROUPS:
                console.print(
                    f"[red]Invalid age group: {ag}[/red]\n"
                    f"[dim]Valid age groups: {', '.join(VALID_AGE_GROUPS)}[/dim]"
                )
                raise typer.Exit(code=1)

    # Default output filename
    output_path = output or f"{division.lower()}-clubs.json"

    display_header()

    console.print(
        Panel(
            f"Division: [bold]{division}[/bold]\n"
            f"League: [bold]{league}[/bold]\n"
            f"Age Groups: [bold]{', '.join(parsed_age_groups or ['U13', 'U14', 'U15', 'U16', 'U17', 'U19'])}[/bold]\n"
            f"Output: [bold]{output_path}[/bold]",
            title="Division Discovery",
            border_style="cyan",
        )
    )

    discoverer = DivisionDiscoverer(
        division=division,
        league=league,
        headless=headless,
        age_groups=parsed_age_groups,
    )

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task(f"Discovering teams in {division}...", total=None)
            clubs = asyncio.run(discoverer.discover())

        if not clubs:
            console.print(f"[yellow]No teams found in {division} division.[/yellow]")
            raise typer.Exit(code=0)

        # Serialize to JSON
        clubs_data = [club.model_dump() for club in clubs]

        with open(output_path, "w") as f:
            json.dump(clubs_data, f, indent=2)

        # Display summary
        total_teams = len(clubs)
        all_age_groups: set[str] = set()
        for club in clubs:
            for team in club.teams:
                all_age_groups.update(team.age_groups)

        summary_table = Table(show_header=True, header_style="bold magenta", box=None)
        summary_table.add_column("Club", style="green", min_width=30)
        summary_table.add_column("Age Groups", style="cyan")

        for club in clubs:
            for team in club.teams:
                summary_table.add_row(
                    club.club_name,
                    ", ".join(team.age_groups),
                )

        console.print(
            Panel(
                summary_table,
                title=f"Discovered {total_teams} Clubs in {division}",
                border_style="green",
            )
        )
        console.print(f"\n[green]Saved to {output_path}[/green]")
        console.print(
            f"[dim]Age groups covered: {', '.join(sorted(all_age_groups, key=lambda ag: int(ag[1:])))}[/dim]"
        )
        console.print(
            "\n[dim]Next steps:[/dim]\n"
            f"  1. Review and edit {output_path} (add location, website, is_pro_academy)\n"
            "  2. Merge entries into clubs.json\n"
            "  3. Run setup_leagues_divisions.py to create the division\n"
            "  4. Run manage_clubs.py sync to create clubs/teams in DB\n"
        )

    except typer.Exit:
        raise
    except Exception as e:
        handle_cli_error(e, verbose)
        raise typer.Exit(code=1) from None


if __name__ == "__main__":
    app()
