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
from datetime import date, timedelta
from pathlib import Path
from typing import Annotated, Optional

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

from src.api.missing_table_client import (  # noqa: E402
    MissingTableAPIError,
    MissingTableClient,
)
from src.cli.env_config import (  # noqa: E402
    display_current_config,
    interactive_setup,
    set_variable,
    validate_config,
)
from src.scraper.config import ScrapingConfig  # noqa: E402
from src.scraper.mls_scraper import MLSScraper, MLSScraperError  # noqa: E402
from src.scraper.models import Match  # noqa: E402

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
DEFAULT_DIVISION = "Northeast"
DEFAULT_START_OFFSET = 1  # 1 day backward from today = Yesterday
DEFAULT_END_OFFSET = 1  # 1 day forward from today = Tomorrow
DEFAULT_DAYS = 3  # Keep for upcoming command backward compatibility

# Valid options
VALID_AGE_GROUPS = ["U13", "U14", "U15", "U16", "U17", "U18", "U19"]
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
]


# Team name mappings for display (matches api_integration mappings)
TEAM_NAME_MAPPINGS = {
    "Intercontinental Football Academy of New England": "IFA",
}


def normalize_team_name_for_display(team_name: str) -> str:
    """Normalize team names for consistent display."""
    return TEAM_NAME_MAPPINGS.get(team_name, team_name)


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


async def check_missing_table_api(verbose: bool = False) -> bool:
    """Check if missing-table API is healthy and ready."""
    try:
        client = MissingTableClient()

        if verbose:
            console.print("🏥 Checking missing-table API health...")

        # Perform health check
        health = await client.health_check(full=False)

        if verbose:
            console.print(f"✅ API Health: {health.status}")
            if health.version:
                console.print(f"   Version: {health.version}")

        return health.status.lower() == "healthy"

    except MissingTableAPIError as e:
        if verbose:
            console.print(f"❌ Missing-table API error: {e}")
            if e.status_code:
                console.print(f"   Status: {e.status_code}")
        else:
            console.print(
                "⚠️  Missing-table API not available (continuing with scraping only)"
            )
        return False

    except Exception as e:
        if verbose:
            console.print(f"💥 Unexpected API error: {e}")
        else:
            console.print(
                "⚠️  Missing-table API check failed (continuing with scraping only)"
            )
        return False


def create_config(
    age_group: str,
    division: str,
    start_offset: int,
    end_offset: int,
    club: str = "",
    competition: str = "",
    verbose: bool = False,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> ScrapingConfig:
    """Create scraping configuration from CLI parameters."""

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
        # Use relative offsets (enhanced with negative support for --end)
        today = date.today()
        start_date = today - timedelta(
            days=start_offset
        )  # --start: backward from today

        # --end: positive = forward, negative = backward from today
        if end_offset >= 0:
            end_date = today + timedelta(days=end_offset)  # Forward
        else:
            end_date = today - timedelta(days=abs(end_offset))  # Backward

    return ScrapingConfig(
        age_group=age_group,
        club=club,
        competition=competition,
        division=division,
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

    config_table.add_row("Age Group", config.age_group)
    config_table.add_row("Division", config.division)
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
    table.add_column("Match ID", style="dim", width=10)
    table.add_column("Date", style="cyan", width=12)
    table.add_column("Time", style="dim", width=8)
    table.add_column("Home Team", style="green", min_width=20)
    table.add_column("Away Team", style="red", min_width=20)
    table.add_column("Score/Status", style="yellow", width=12, justify="center")
    table.add_column("Venue", style="blue", min_width=20)

    # Sort matches by date
    from datetime import datetime

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
            if match.match_status == "played":
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

        # Format match_id (show last 8 characters for readability)
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
    played_matches = len([m for m in matches if m.match_status == "played"])
    in_progress_matches = len([m for m in matches if m.match_status == "in_progress"])
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
    if in_progress_matches > 0:
        stats_table.add_row(
            "🔄 In Progress",
            str(in_progress_matches),
            f"{in_progress_matches / total_matches * 100:.0f}%",
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


def display_api_results(api_results: dict, api_healthy: bool) -> None:
    """Display API integration results in a prominent panel."""
    if not api_results:
        if api_healthy:
            console.print(
                Panel(
                    "[yellow]⚠️  API was available but no matches were posted[/yellow]",
                    title="📡 Missing-table API Integration",
                    border_style="yellow",
                )
            )
        else:
            console.print(
                Panel(
                    "[dim]⚠️  API not available - matches not posted[/dim]",
                    title="📡 Missing-table API Integration",
                    border_style="dim",
                )
            )
        return

    posted = api_results.get("posted", 0)
    errors = api_results.get("errors", 0)
    skipped = api_results.get("skipped", 0)
    duplicates = api_results.get("duplicates", 0)
    api_error = api_results.get("api_error")

    # If there's a specific API error, show it prominently
    if api_error:
        console.print(
            Panel(
                f"[red]❌ API Connection Failed[/red]\n\n{api_error}\n\n[dim]Matches were scraped successfully but could not be posted to missing-table API.[/dim]",
                title="📡 Missing-table API Integration - Connection Error",
                border_style="red",
            )
        )
        return

    # Create API results table
    api_table = Table(show_header=False, box=None, padding=(0, 1))
    api_table.add_column("Status", style="cyan", width=20)
    api_table.add_column("Count", style="white", justify="right", width=8)

    updated = api_results.get("updated", 0)

    if posted > 0:
        api_table.add_row("✅ Successfully posted", str(posted))
    if updated > 0:
        api_table.add_row("📝 Scores updated", str(updated))
    if duplicates > 0:
        api_table.add_row("🔄 Skipped duplicates", str(duplicates))
    if errors > 0:
        api_table.add_row("❌ Failed to post", str(errors))
    if skipped > 0:
        api_table.add_row("⏭️  Skipped (other)", str(skipped))

    if not posted and not errors and not skipped and not duplicates and not updated:
        api_table.add_row("ℹ️  No action taken", "0")

    # Determine panel style based on results
    if errors > 0 and posted == 0 and updated == 0:
        title_style = "red"
        title = "📡 Missing-table API Integration - ❌ Failed"
    elif errors > 0:
        title_style = "yellow"
        title = "📡 Missing-table API Integration - ⚠️  Partial Success"
    elif posted > 0 or duplicates > 0 or updated > 0:
        title_style = "green"
        title = "📡 Missing-table API Integration - ✅ Success"
    else:
        title_style = "dim"
        title = "📡 Missing-table API Integration - ℹ️  No Changes"

    console.print(Panel(api_table, title=title, border_style=title_style))


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
    enable_api_integration: bool = True,
) -> tuple[list[Match], bool, dict]:
    """Run the scraper with progress indication and API health check.

    Returns:
        Tuple of (matches, api_healthy, api_results)
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
    api_healthy = False

    # Disable progress spinner in container environments (NO_COLOR=1)
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
        disable=not use_rich,  # Disable progress bar when NO_COLOR is set
    ) as progress:
        # Check API health first
        health_task = progress.add_task("🏥 Checking missing-table API...", total=None)
        try:
            api_healthy = await check_missing_table_api(verbose=verbose)
            if api_healthy:
                progress.update(health_task, description="✅ API ready for integration")
            else:
                progress.update(
                    health_task, description="⚠️  API not available (scraping only)"
                )
        except Exception as e:
            progress.update(health_task, description="❌ API check failed")
            if verbose:
                console.print(f"API health check error: {e}")
        finally:
            # Remove the health check task to prevent it from being repeatedly displayed
            progress.remove_task(health_task)

        # Add scraping progress task
        scrape_task = progress.add_task("🌐 Initializing browser...", total=None)

        try:
            scraper = MLSScraper(
                config, headless=headless, enable_api_integration=enable_api_integration
            )

            progress.update(scrape_task, description="🔍 Scraping matches...")
            matches = await scraper.scrape_matches()

            # Get API results from scraper (includes posted, errors, skipped, duplicates, updated)
            api_results = (
                scraper.api_results
                if scraper.api_results
                else {
                    "posted": 0,
                    "errors": 0,
                    "skipped": 0,
                    "duplicates": 0,
                    "updated": 0,
                }
            )

            progress.update(scrape_task, description="✅ Scraping completed!")
            progress.remove_task(scrape_task)

        except MLSScraperError as e:
            progress.update(scrape_task, description=f"❌ Scraping failed: {e}")
            raise
        except Exception as e:
            error_str = str(e).lower()
            if "cannot connect to missing-table api" in error_str:
                progress.update(
                    scrape_task, description="⚠️  API connection failed, continuing..."
                )
                # Still return matches, just without API integration
                api_results = {
                    "posted": 0,
                    "errors": scraper.execution_metrics.api_calls_failed,
                    "skipped": 0,
                    "api_error": str(e),
                }
                return matches, False, api_results
            else:
                progress.update(scrape_task, description=f"💥 Unexpected error: {e}")
                raise

    return matches, api_healthy, api_results


@app.command()
def scrape(
    age_group: Annotated[
        str, typer.Option("--age-group", "-a", help="Age group to scrape")
    ] = DEFAULT_AGE_GROUP,
    division: Annotated[
        str, typer.Option("--division", "-d", help="Division to scrape")
    ] = DEFAULT_DIVISION,
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
    api_integration: Annotated[
        bool,
        typer.Option(
            "--api/--no-api", help="Enable posting matches to missing-table API"
        ),
    ] = True,
    save_file: Annotated[
        Optional[str],
        typer.Option(
            "--save", help="Save matches to JSON file (e.g., --save games.json)"
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

    if division not in VALID_DIVISIONS:
        console.print(f"[red]❌ Invalid division: {division}[/red]")
        console.print(f"Valid options: {', '.join(VALID_DIVISIONS)}")
        raise typer.Exit(1)

    if not quiet:
        display_header()

    # Create configuration
    config = create_config(
        age_group, division, start, end, club, competition, verbose, from_date, to_date
    )

    if not quiet:
        display_config_summary(config)
        console.print()

    try:
        # Run scraper with execution time tracking
        from src.utils.metrics import get_metrics

        metrics = get_metrics()

        with metrics.time_execution():
            matches, api_healthy, api_results = asyncio.run(
                run_scraper(config, verbose, headless, api_integration)
            )

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
                    if match.match_status == "played"
                    else "⏰"
                    if match.match_status == "scheduled"
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

            # Show API integration results prominently
            if api_integration:
                display_api_results(api_results, api_healthy)

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
    config = create_config(age_group, division, 0, days, verbose=verbose)

    try:
        matches, api_healthy, api_results = asyncio.run(run_scraper(config, verbose))
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
        age_group, division, start_offset, end_offset, club, competition, verbose=False
    )
    display_config_summary(config)

    if not Confirm.ask("\nProceed with scraping?", default=True):
        console.print("Cancelled.")
        return

    try:
        matches, api_healthy, api_results = asyncio.run(run_scraper(config, verbose))

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
    from datetime import datetime

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
            if match.match_status == "played"
            else "⏰"
            if match.match_status == "scheduled"
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


# Create cache subapp
cache_app = typer.Typer(help="🗄️ Team cache management commands")
app.add_typer(cache_app, name="cache")


@cache_app.command("load")
def cache_load(
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Show detailed logs")
    ] = False,
) -> None:
    """Load teams into cache and display statistics."""
    setup_environment(verbose)

    if not verbose:
        display_header()

    async def load_cache() -> None:
        try:
            from src.api.missing_table_client import MissingTableClient
            from src.scraper.api_integration import MatchAPIIntegrator

            # Create API client and integrator
            client = MissingTableClient()
            integrator = MatchAPIIntegrator(client)

            console.print("🔄 Loading teams cache...")

            # Preload cache
            result = await integrator.preload_teams_cache()

            if result.get("success", True):  # True for already_loaded case
                if result.get("already_loaded"):
                    console.print("[yellow]✓ Cache already loaded![/yellow]")
                else:
                    console.print("[green]✅ Cache loaded successfully![/green]")

                # Display statistics
                stats = integrator.get_cache_stats()

                stats_table = Table(show_header=False, box=None)
                stats_table.add_column("Metric", style="cyan")
                stats_table.add_column("Value", style="white")

                stats_table.add_row("Teams loaded", str(stats["team_count"]))
                stats_table.add_row("Load time", f"{stats['load_time']:.3f}s")
                stats_table.add_row(
                    "Cache status", "✅ Loaded" if stats["loaded"] else "❌ Not loaded"
                )

                console.print(
                    Panel(
                        stats_table, title="📊 Cache Statistics", border_style="green"
                    )
                )
            else:
                console.print(
                    f"[red]❌ Cache loading failed: {result.get('error', 'Unknown error')}[/red]"
                )

        except Exception as e:
            console.print(f"[red]❌ Error loading cache: {e}[/red]")

    asyncio.run(load_cache())


@cache_app.command("status")
def cache_status(
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Show detailed logs")
    ] = False,
) -> None:
    """Show current cache status and statistics."""
    setup_environment(verbose)

    if not verbose:
        display_header()

    async def show_status() -> None:
        try:
            from src.api.missing_table_client import MissingTableClient
            from src.scraper.api_integration import MatchAPIIntegrator

            # Create API client and integrator
            client = MissingTableClient()
            integrator = MatchAPIIntegrator(client)

            # Get cache statistics
            stats = integrator.get_cache_stats()

            # Create status table
            status_table = Table(show_header=False, box=None)
            status_table.add_column("Metric", style="cyan")
            status_table.add_column("Value", style="white")

            status_table.add_row(
                "Cache loaded", "✅ Yes" if stats["loaded"] else "❌ No"
            )
            status_table.add_row("Teams in cache", str(stats["team_count"]))
            if stats["load_time"]:
                status_table.add_row("Last load time", f"{stats['load_time']:.3f}s")
            if stats["hit_count"] > 0 or stats["miss_count"] > 0:
                status_table.add_row("Cache hits", str(stats["hit_count"]))
                status_table.add_row("Cache misses", str(stats["miss_count"]))
                status_table.add_row("Hit rate", f"{stats['hit_rate']:.1%}")

            # Determine border color based on status
            border_color = "green" if stats["loaded"] else "red"
            title = (
                "📊 Cache Status - ✅ Active"
                if stats["loaded"]
                else "📊 Cache Status - ❌ Not Loaded"
            )

            console.print(Panel(status_table, title=title, border_style=border_color))

        except Exception as e:
            console.print(f"[red]❌ Error getting cache status: {e}[/red]")

    asyncio.run(show_status())


@cache_app.command("clear")
def cache_clear(
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Show detailed logs")
    ] = False,
) -> None:
    """Clear the teams cache for testing purposes."""
    setup_environment(verbose)

    if not verbose:
        display_header()

    async def clear_cache() -> None:
        try:
            from src.api.missing_table_client import MissingTableClient
            from src.scraper.api_integration import MatchAPIIntegrator

            # Create API client and integrator
            client = MissingTableClient()
            integrator = MatchAPIIntegrator(client)

            # Clear cache
            integrator.clear_cache()
            console.print("[yellow]🗑️  Cache cleared successfully![/yellow]")

        except Exception as e:
            console.print(f"[red]❌ Error clearing cache: {e}[/red]")

    asyncio.run(clear_cache())


@cache_app.command("test")
def cache_test(
    teams: Annotated[
        str, typer.Option("--teams", help="Comma-separated list of team names to test")
    ] = "Boston Bolts,New York City FC,IFA",
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Show detailed logs")
    ] = False,
) -> None:
    """Test cache performance with specific team names."""
    setup_environment(verbose)

    if not verbose:
        display_header()

    async def test_teams() -> None:
        try:
            import time

            from src.api.missing_table_client import MissingTableClient
            from src.scraper.api_integration import MatchAPIIntegrator

            # Create API client and integrator
            client = MissingTableClient()
            integrator = MatchAPIIntegrator(client)

            team_list = [team.strip() for team in teams.split(",")]

            console.print(f"🧪 Testing cache with {len(team_list)} teams...")
            console.print(f"Teams: {', '.join(team_list)}")
            console.print()

            # Load cache first
            console.print("🔄 Loading cache...")
            cache_result = await integrator.preload_teams_cache()

            if not cache_result.get("success", True):
                console.print(
                    "[yellow]⚠️ Cache loading failed, testing without cache[/yellow]"
                )

            # Test each team
            results_table = Table(show_header=True, header_style="bold magenta")
            results_table.add_column("Team Name", style="cyan")
            results_table.add_column("Found", style="white")
            results_table.add_column("Team ID", style="green")
            results_table.add_column("Status", style="yellow")

            for team_name in team_list:
                start_time = time.time()
                team_id = await integrator._find_team_by_name(team_name)
                lookup_time = time.time() - start_time

                if team_id:
                    results_table.add_row(
                        team_name,
                        "✅ Yes",
                        str(team_id),
                        f"Found in {lookup_time:.3f}s",
                    )
                else:
                    results_table.add_row(
                        team_name, "❌ No", "-", f"Not found ({lookup_time:.3f}s)"
                    )

            console.print(Panel(results_table, title="🧪 Team Lookup Test Results"))

            # Show final cache stats
            stats = integrator.get_cache_stats()
            if stats["hit_count"] > 0 or stats["miss_count"] > 0:
                console.print("\n📊 Cache Performance:")
                console.print(f"   Hits: {stats['hit_count']}")
                console.print(f"   Misses: {stats['miss_count']}")
                console.print(f"   Hit Rate: {stats['hit_rate']:.1%}")

        except Exception as e:
            console.print(f"[red]❌ Error testing teams: {e}[/red]")

    asyncio.run(test_teams())


@cache_app.command("benchmark")
def cache_benchmark(
    teams: Annotated[
        str,
        typer.Option("--teams", help="Comma-separated list of team names to benchmark"),
    ] = "Boston Bolts,New York City FC,IFA,Austin FC Academy,Real Salt Lake Academy",
    iterations: Annotated[
        int, typer.Option("--iterations", help="Number of iterations per test")
    ] = 3,
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Show detailed logs")
    ] = False,
) -> None:
    """Benchmark cache performance vs traditional individual lookups."""
    setup_environment(verbose)

    if not verbose:
        display_header()

    async def benchmark() -> None:
        try:
            import time

            from src.api.missing_table_client import MissingTableClient
            from src.scraper.api_integration import MatchAPIIntegrator

            # Create API client and integrator
            client = MissingTableClient()
            integrator = MatchAPIIntegrator(client)

            team_list = [team.strip() for team in teams.split(",")]

            console.print("🏁 Benchmarking cache performance...")
            console.print(f"Teams: {len(team_list)} | Iterations: {iterations}")
            console.print()

            # Test 1: Traditional individual lookups (clear cache first)
            console.print("🔄 Testing traditional individual lookups...")
            integrator.clear_cache()

            traditional_times = []
            for i in range(iterations):
                integrator.clear_cache()  # Clear cache between iterations
                start_time = time.time()

                # Do individual lookups without cache
                for team_name in team_list:
                    await integrator._find_team_by_name(team_name)

                iteration_time = time.time() - start_time
                traditional_times.append(iteration_time)
                console.print(f"   Iteration {i + 1}: {iteration_time:.3f}s")

            avg_traditional = sum(traditional_times) / len(traditional_times)

            console.print()

            # Test 2: Cache-optimized lookups
            console.print("🚀 Testing cache-optimized lookups...")

            cached_times = []
            for i in range(iterations):
                integrator.clear_cache()  # Start fresh
                start_time = time.time()

                # Preload cache once, then do lookups
                await integrator.preload_teams_cache()
                for team_name in team_list:
                    await integrator._find_team_by_name(team_name)

                iteration_time = time.time() - start_time
                cached_times.append(iteration_time)
                console.print(f"   Iteration {i + 1}: {iteration_time:.3f}s")

            avg_cached = sum(cached_times) / len(cached_times)

            console.print()

            # Results comparison
            improvement = ((avg_traditional - avg_cached) / avg_traditional) * 100
            speedup = avg_traditional / avg_cached

            results_table = Table(show_header=True, header_style="bold magenta")
            results_table.add_column("Method", style="cyan")
            results_table.add_column("Avg Time", style="white")
            results_table.add_column("Min Time", style="green")
            results_table.add_column("Max Time", style="red")
            results_table.add_column("Performance", style="yellow")

            results_table.add_row(
                "Traditional Lookups",
                f"{avg_traditional:.3f}s",
                f"{min(traditional_times):.3f}s",
                f"{max(traditional_times):.3f}s",
                "Baseline",
            )

            results_table.add_row(
                "Cache-Optimized",
                f"{avg_cached:.3f}s",
                f"{min(cached_times):.3f}s",
                f"{max(cached_times):.3f}s",
                f"{speedup:.1f}x faster"
                if improvement > 0
                else f"{abs(speedup):.1f}x slower",
            )

            console.print(Panel(results_table, title="🏁 Benchmark Results"))

            # Summary
            if improvement > 0:
                console.print(
                    f"\n🎉 [green]Cache optimization achieved {improvement:.1f}% improvement![/green]"
                )
                console.print(
                    f"   Cache method is {speedup:.1f}x faster than traditional lookups"
                )
            else:
                console.print(
                    f"\n⚠️ [yellow]Cache method was {abs(improvement):.1f}% slower[/yellow]"
                )
                console.print(
                    "   Consider investigating network conditions or API response times"
                )

            # Show final cache stats
            stats = integrator.get_cache_stats()
            console.print(
                f"\n📊 Final cache stats: {stats['hit_count']} hits, {stats['miss_count']} misses"
            )

        except Exception as e:
            console.print(f"[red]❌ Benchmark failed: {e}[/red]")

    asyncio.run(benchmark())


@app.command()
def demo() -> None:
    """
    🎭 Demo mode with sample data to test the CLI interface.

    Shows how the CLI looks with sample match data without scraping.
    """
    from datetime import datetime

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
            wait_strategies = ["load", "domcontentloaded", "networkidle"]

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


if __name__ == "__main__":
    app()
