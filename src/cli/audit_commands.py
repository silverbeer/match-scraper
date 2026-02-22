"""
Audit CLI commands for viewing and validating match processing activity.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Optional

import typer
from rich.console import Console
from rich.table import Table

from src.models.audit import EventType

app = typer.Typer(help="Audit log management commands")
console = Console()


def _get_audit_directory() -> Path:
    """Get the audit log directory path."""
    k8s_path = Path("/var/log/scraper/audit")
    local_path = Path("./audit")

    if k8s_path.exists():
        return k8s_path
    else:
        return local_path


def _get_audit_file(date_str: str) -> Path:
    """Get the audit file path for a specific date."""
    audit_dir = _get_audit_directory()
    return audit_dir / f"match-audit-{date_str}.jsonl"


def _load_audit_entries(file_path: Path) -> list[dict]:
    """Load audit entries from JSONL file."""
    if not file_path.exists():
        return []

    entries = []
    try:
        with open(file_path) as f:
            for line in f:
                if line.strip():
                    entries.append(json.loads(line))
    except Exception as e:
        console.print(f"[red]Error loading audit file: {e}[/red]")
        return []

    return entries


@app.command()
def view(
    date: Annotated[
        Optional[str],
        typer.Option("--date", "-d", help="Date to view (YYYY-MM-DD, default: today)"),
    ] = None,
    league: Annotated[
        Optional[str],
        typer.Option("--league", "-l", help="Filter by league (Homegrown/Academy)"),
    ] = None,
    event_type: Annotated[
        Optional[str],
        typer.Option("--event-type", "-e", help="Filter by event type"),
    ] = None,
    run_id: Annotated[
        Optional[str],
        typer.Option("--run-id", "-r", help="Filter by specific run ID"),
    ] = None,
    match_id: Annotated[
        Optional[str],
        typer.Option(
            "--match-id", "-m", help="Filter by correlation_id/external_match_id"
        ),
    ] = None,
    changes_only: Annotated[
        bool,
        typer.Option("--changes-only", help="Show only match_updated events"),
    ] = False,
    output_format: Annotated[
        str,
        typer.Option("--format", "-f", help="Output format (text/json)"),
    ] = "text",
) -> None:
    """View audit log entries."""
    # Default to today's date
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    audit_file = _get_audit_file(date)

    if not audit_file.exists():
        console.print(
            f"[yellow]No audit file found for {date}[/yellow]\nExpected: {audit_file}"
        )
        raise typer.Exit(1)

    entries = _load_audit_entries(audit_file)

    if not entries:
        console.print(f"[yellow]No audit entries found for {date}[/yellow]")
        raise typer.Exit(0)

    # Apply filters
    filtered_entries = entries

    if league:
        filtered_entries = [
            e
            for e in filtered_entries
            if e.get("run_metadata", {}).get("league") == league
        ]

    if event_type:
        filtered_entries = [
            e for e in filtered_entries if e.get("event_type") == event_type
        ]

    if run_id:
        filtered_entries = [e for e in filtered_entries if e.get("run_id") == run_id]

    if match_id:
        filtered_entries = [
            e for e in filtered_entries if e.get("correlation_id") == match_id
        ]

    if changes_only:
        filtered_entries = [
            e
            for e in filtered_entries
            if e.get("event_type") == EventType.MATCH_UPDATED.value
        ]

    if not filtered_entries:
        console.print("[yellow]No matching audit entries found[/yellow]")
        raise typer.Exit(0)

    # Output format
    if output_format == "json":
        for entry in filtered_entries:
            print(json.dumps(entry))
    else:
        _display_audit_entries_text(filtered_entries, date)


def _display_audit_entries_text(entries: list[dict[str, Any]], date_str: str) -> None:
    """Display audit entries in human-readable text format."""
    console.print(f"\n[bold cyan]=== Match Audit Log: {date_str} ===[/bold cyan]\n")

    # Group by run_id
    runs: dict[str | None, list[dict[str, Any]]] = {}
    for entry in entries:
        run_id = entry.get("run_id")
        if run_id not in runs:
            runs[run_id] = []
        runs[run_id].append(entry)

    # Display each run
    total_discovered = 0
    total_updated = 0
    total_unchanged = 0
    total_submitted = 0
    total_failed = 0

    for run_id, run_entries in runs.items():
        # Find run metadata from any entry in this run
        run_meta = None
        summary = None
        for entry in run_entries:
            if entry.get("run_metadata"):
                run_meta = entry["run_metadata"]
            if entry.get("summary"):
                summary = entry["summary"]

        # Display run header
        if run_meta:
            league = run_meta.get("league", "Unknown")
            age_group = run_meta.get("age_group", "")
            division = run_meta.get("division", "")
            date_range = run_meta.get("date_range", "")
            console.print(
                f"[bold]Run: {run_id}[/bold] | {league} | {age_group} {division} | {date_range}"
            )
        else:
            console.print(f"[bold]Run: {run_id}[/bold]")

        # Display events
        for entry in run_entries:
            event_type = entry.get("event_type")
            timestamp = entry.get("timestamp", "")
            time_str = timestamp.split("T")[1][:8] if "T" in timestamp else ""
            correlation_id = entry.get("correlation_id")

            if event_type == EventType.RUN_STARTED.value:
                console.print(f"  {time_str} [green]✓[/green] run_started")

            elif event_type == EventType.RUN_COMPLETED.value:
                summary = entry.get("summary", {})
                console.print(
                    f"  {time_str} [green]✓[/green] run_completed | "
                    f"{summary.get('total_matches', 0)} matches "
                    f"({summary.get('discovered', 0)} discovered, "
                    f"{summary.get('updated', 0)} updated, "
                    f"{summary.get('unchanged', 0)} unchanged)"
                )

            elif event_type == EventType.MATCH_DISCOVERED.value:
                match_data = entry.get("match_data", {})
                home = match_data.get("home_team", "?")
                away = match_data.get("away_team", "?")
                status = match_data.get("match_status", "?")
                match_date = match_data.get("match_date", "?")
                console.print(
                    f"  {time_str} [green]✓[/green] match_discovered | "
                    f"#{correlation_id} | {home} vs {away} | {status} | {match_date}"
                )
                total_discovered += 1

            elif event_type == EventType.MATCH_UPDATED.value:
                match_data = entry.get("match_data", {})
                changes = entry.get("changes", {})
                home = match_data.get("home_team", "?")
                away = match_data.get("away_team", "?")
                home_score = match_data.get("home_score")
                away_score = match_data.get("away_score")
                status = match_data.get("match_status", "?")

                score_str = ""
                if home_score is not None and away_score is not None:
                    score_str = f" | {home_score}-{away_score}"

                console.print(
                    f"  {time_str} [yellow]⟳[/yellow] match_updated | "
                    f"#{correlation_id} | {home} vs {away}{score_str} | {status}"
                )

                # Display changes
                if changes:
                    change_strs = []
                    for field, change in changes.items():
                        from_val = change.get("from")
                        to_val = change.get("to")
                        change_strs.append(f"{field} ({from_val} → {to_val})")
                    console.print(
                        f"           [dim]└─ Changes: {', '.join(change_strs)}[/dim]"
                    )

                total_updated += 1

            elif event_type == EventType.MATCH_UNCHANGED.value:
                total_unchanged += 1
                # Don't display unchanged matches unless specifically filtered

            elif event_type == EventType.QUEUE_SUBMITTED.value:
                task_id = entry.get("queue_task_id", "")[:8]
                console.print(
                    f"  {time_str} [green]✓[/green] queue_submitted | "
                    f"#{correlation_id} | task:{task_id}"
                )
                total_submitted += 1

            elif event_type == EventType.QUEUE_FAILED.value:
                error = entry.get("error_message", "Unknown error")
                console.print(
                    f"  {time_str} [red]✗[/red] queue_failed | "
                    f"#{correlation_id} | {error}"
                )
                total_failed += 1

        console.print()  # Blank line between runs

    # Display summary
    console.print(
        f"[bold]Summary:[/bold] {total_discovered + total_updated + total_unchanged} total matches "
        f"({total_discovered} discovered, {total_updated} updated, {total_unchanged} unchanged), "
        f"{total_submitted} submitted to queue, {total_failed} failures"
    )


@app.command()
def validate(
    date: Annotated[
        Optional[str],
        typer.Option(
            "--date", "-d", help="Date to validate (YYYY-MM-DD, default: today)"
        ),
    ] = None,
    league: Annotated[
        Optional[str],
        typer.Option("--league", "-l", help="Validate specific league only"),
    ] = None,
    backend_url: Annotated[
        Optional[str],
        typer.Option("--backend-url", help="MT backend API URL (default: from env)"),
    ] = None,
) -> None:
    """
    Validate audit log against Missing Table backend.

    NOTE: This is a basic validation command. Full implementation requires
    MT backend API integration.
    """
    # Default to today's date
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    audit_file = _get_audit_file(date)

    if not audit_file.exists():
        console.print(
            f"[yellow]No audit file found for {date}[/yellow]\nExpected: {audit_file}"
        )
        raise typer.Exit(1)

    entries = _load_audit_entries(audit_file)

    if not entries:
        console.print(f"[yellow]No audit entries found for {date}[/yellow]")
        raise typer.Exit(0)

    # Extract matches from audit log
    matches_in_audit = {}
    for entry in entries:
        if entry.get("event_type") in [
            EventType.MATCH_DISCOVERED.value,
            EventType.MATCH_UPDATED.value,
        ]:
            correlation_id = entry.get("correlation_id")
            match_data = entry.get("match_data", {})
            if correlation_id:
                matches_in_audit[correlation_id] = match_data

    console.print(f"\n[bold cyan]=== Audit Validation: {date} ===[/bold cyan]\n")
    console.print(f"Found {len(matches_in_audit)} matches in audit log")

    # TODO: Implement MT backend API integration
    console.print("\n[yellow]⚠ Backend validation not yet implemented[/yellow]")
    console.print(
        "[dim]To fully validate, compare audit log entries against MT backend database[/dim]"
    )
    console.print(f"[dim]Audit file: {audit_file}[/dim]")

    # Display match summary by league
    if league:
        league_matches = [
            m for m in matches_in_audit.values() if m.get("league") == league
        ]
        console.print(f"\n{league} League: {len(league_matches)} matches")
    else:
        leagues = {
            m.get("league") for m in matches_in_audit.values() if m.get("league")
        }
        for league_name in sorted(leagues):
            league_matches = [
                m for m in matches_in_audit.values() if m.get("league") == league_name
            ]
            console.print(f"{league_name} League: {len(league_matches)} matches")


@app.command()
def stats(
    date: Annotated[
        Optional[str],
        typer.Option(
            "--date", "-d", help="Date to analyze (YYYY-MM-DD, default: today)"
        ),
    ] = None,
) -> None:
    """Show statistics for audit logs."""
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    audit_file = _get_audit_file(date)

    if not audit_file.exists():
        console.print(
            f"[yellow]No audit file found for {date}[/yellow]\nExpected: {audit_file}"
        )
        raise typer.Exit(1)

    entries = _load_audit_entries(audit_file)

    if not entries:
        console.print(f"[yellow]No audit entries found for {date}[/yellow]")
        raise typer.Exit(0)

    # Calculate statistics
    total_entries = len(entries)
    run_ids: set[str] = set()
    discovered = 0
    updated = 0
    unchanged = 0
    queue_submitted = 0
    queue_failed = 0
    leagues: dict[str, int] = {}

    for entry in entries:
        run_id = entry.get("run_id")
        if run_id:
            run_ids.add(run_id)

        event_type = entry.get("event_type")
        if event_type == EventType.MATCH_DISCOVERED.value:
            discovered += 1
        elif event_type == EventType.MATCH_UPDATED.value:
            updated += 1
        elif event_type == EventType.MATCH_UNCHANGED.value:
            unchanged += 1
        elif event_type == EventType.QUEUE_SUBMITTED.value:
            queue_submitted += 1
        elif event_type == EventType.QUEUE_FAILED.value:
            queue_failed += 1

        # Track by league
        league = entry.get("run_metadata", {}).get("league")
        if league:
            if league not in leagues:
                leagues[league] = 0
            leagues[league] += 1

    # Display statistics
    console.print(f"\n[bold cyan]=== Audit Statistics: {date} ===[/bold cyan]\n")

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Metric", style="cyan")
    table.add_column("Count", justify="right", style="green")

    table.add_row("Total Entries", str(total_entries))
    table.add_row("Scraping Runs", str(len(run_ids)))
    table.add_row("Matches Discovered", str(discovered))
    table.add_row("Matches Updated", str(updated))
    table.add_row("Matches Unchanged", str(unchanged))
    table.add_row("Queue Submitted", str(queue_submitted))
    table.add_row("Queue Failed", str(queue_failed))

    console.print(table)

    if leagues:
        console.print("\n[bold]By League:[/bold]")
        for league_name, count in sorted(leagues.items()):
            console.print(f"  {league_name}: {count} entries")


if __name__ == "__main__":
    app()
