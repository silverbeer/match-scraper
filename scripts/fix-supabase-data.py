#!/usr/bin/env python3
"""
Script to fix existing data in Supabase database.

This script identifies and fixes games that were incorrectly marked as "completed" 
with 0-0 scores when they should be "TBD" or "scheduled" based on the date logic.

Usage:
    python scripts/fix-supabase-data.py --help
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone
from typing import List, Optional

import httpx
from rich.console import Console
from rich.table import Table

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.scraper.config import load_config

console = Console()


class SupabaseDataFixer:
    """Handles fixing incorrect data in Supabase database."""
    
    def __init__(self, api_base_url: str, api_token: str):
        self.api_base_url = api_base_url.rstrip('/')
        self.api_token = api_token
        # Import MissingTableClient here to avoid circular imports
        from src.api.missing_table_client import MissingTableClient
        self.client = MissingTableClient(api_base_url, api_token)
    
    async def get_games_with_placeholder_scores(self) -> List[dict]:
        """Get games that have 0-0 scores and might be placeholders."""
        try:
            games = await self.client.list_games()
            
            console.print(f"[blue]Found {len(games)} total games in database[/blue]")
            
            # Show all games for debugging
            if games:
                console.print("\n[blue]All games in database:[/blue]")
                for i, game in enumerate(games[:5]):  # Show first 5
                    console.print(f"  {i+1}. ID: {game.get('id')}, Date: {game.get('date')}, "
                                f"Home: {game.get('home_team', 'N/A')}, Away: {game.get('away_team', 'N/A')}, "
                                f"Score: {game.get('home_score', 'N/A')}-{game.get('away_score', 'N/A')}, "
                                f"Status: {game.get('status', 'N/A')}")
                
                # Show the actual structure of one game
                if games:
                    console.print(f"\n[blue]Sample game structure:[/blue]")
                    sample_game = games[0]
                    for key, value in sample_game.items():
                        console.print(f"  {key}: {value}")
                
                if len(games) > 5:
                    console.print(f"  ... and {len(games) - 5} more games")
            
            # Filter for games with 0-0 scores that should be TBD/Scheduled
            placeholder_games = []
            for game in games:
                home_score = game.get('home_score')
                away_score = game.get('away_score')
                game_date = game.get('game_date')
                
                # Look for 0-0 scores that might be placeholders
                if home_score == 0 and away_score == 0:
                    # Check if this is a recent game (today or yesterday) that should be TBD
                    if game_date:
                        try:
                            from datetime import datetime, timezone
                            game_dt = datetime.fromisoformat(game_date.replace('Z', '+00:00'))
                            now = datetime.now(timezone.utc)
                            
                            # If game is today or yesterday with 0-0, it's likely a placeholder
                            days_diff = (now.date() - game_dt.date()).days
                            if days_diff <= 1:  # Today or yesterday
                                placeholder_games.append(game)
                        except Exception as e:
                            console.print(f"[yellow]Warning: Could not parse date {game_date}: {e}[/yellow]")
                            # If we can't parse the date, include it to be safe
                            placeholder_games.append(game)
            
            console.print(f"\n[blue]Found {len(placeholder_games)} games with 0-0 scores marked as completed[/blue]")
            
            return placeholder_games
            
        except Exception as e:
            console.print(f"[red]Error fetching games: {e}[/red]")
            return []
    
    def should_be_tbd(self, game: dict) -> bool:
        """
        Determine if a game should be marked as TBD based on date logic.
        
        Rules:
        - If game date is today or in the past and has 0-0 score: should be TBD
        - If game date is in the future: should be scheduled
        """
        try:
            # Parse game date
            game_date_str = game.get('game_date')  # Updated field name
            if not game_date_str:
                return True  # If no date, assume TBD
            
            # Parse the date (assuming format like "2025-10-04" or "2025-10-04T12:00:00Z")
            if 'T' in game_date_str:
                game_date = datetime.fromisoformat(game_date_str.replace('Z', '+00:00'))
            else:
                game_date = datetime.fromisoformat(game_date_str)
            
            # Get current date
            now = datetime.now(timezone.utc)
            
            # If game is today or in the past with 0-0 score, it should be TBD
            if game_date.date() <= now.date():
                return True
            
            # If game is in the future, it should be scheduled
            return False
            
        except Exception as e:
            console.print(f"[yellow]Warning: Could not parse date for game {game.get('id', 'unknown')}: {e}[/yellow]")
            return True  # Default to TBD if we can't parse
    
    async def fix_game_status(self, game: dict, dry_run: bool = True) -> bool:
        """Fix the status of a single game by clearing placeholder scores."""
        game_id = game.get('id')
        if not game_id:
            console.print(f"[red]Game missing ID: {game}[/red]")
            return False
        
        # Clear the placeholder scores (set to null)
        # Note: match_status field may not be supported by API yet
        update_data = {
            "home_score": None,
            "away_score": None
        }
        
        if dry_run:
            console.print(f"[yellow]DRY RUN:[/yellow] Would update game {game_id}:")
            console.print(f"  Current: home_score={game.get('home_score')}, away_score={game.get('away_score')}")
            console.print(f"  New:     home_score=None, away_score=None")
            console.print(f"  Teams:   {game.get('home_team_name', 'Unknown')} vs {game.get('away_team_name', 'Unknown')}")
            console.print(f"  Date:    {game.get('game_date', 'Unknown')}")
            return True
        
        try:
            # Use the update_score method from MissingTableClient
            response = await self.client.update_score(str(game_id), update_data)
            
            console.print(f"[green]✓[/green] Updated game {game_id}: {game.get('home_team_name', 'Unknown')} vs {game.get('away_team_name', 'Unknown')}")
            return True
            
        except Exception as e:
            console.print(f"[red]✗[/red] Failed to update game {game_id}: {e}")
            return False
    
    async def fix_all_placeholder_games(self, dry_run: bool = True) -> dict:
        """Fix all games with placeholder scores."""
        console.print("[blue]Fetching games with placeholder scores...[/blue]")
        
        placeholder_games = await self.get_games_with_placeholder_scores()
        
        if not placeholder_games:
            console.print("[green]No games with placeholder scores found![/green]")
            return {"total": 0, "fixed": 0, "failed": 0}
        
        console.print(f"[blue]Found {len(placeholder_games)} games with 0-0 scores marked as completed[/blue]")
        
        # Display games in a table
        table = Table(title="Games to Fix")
        table.add_column("ID", style="cyan")
        table.add_column("Date", style="magenta")
        table.add_column("Home Team", style="green")
        table.add_column("Away Team", style="green")
        table.add_column("Current Score", style="red")
        table.add_column("Current Status", style="red")
        table.add_column("New Status", style="yellow")
        
        for game in placeholder_games:
            new_status = "TBD" if self.should_be_tbd(game) else "scheduled"
            table.add_row(
                str(game.get('id', 'N/A')),
                game.get('game_date', 'N/A'),
                game.get('home_team_name', 'N/A'),
                game.get('away_team_name', 'N/A'),
                f"{game.get('home_score', 'N/A')}-{game.get('away_score', 'N/A')}",
                game.get('match_status', 'N/A'),
                new_status
            )
        
        console.print(table)
        
        if dry_run:
            console.print(f"\n[yellow]DRY RUN:[/yellow] Would fix {len(placeholder_games)} games")
            return {"total": len(placeholder_games), "fixed": 0, "failed": 0}
        
        # Confirm before proceeding (skip in non-interactive mode)
        try:
            if not console.input(f"\n[red]Are you sure you want to fix {len(placeholder_games)} games? (yes/no): [/red]").lower().startswith('y'):
                console.print("[yellow]Operation cancelled[/yellow]")
                return {"total": len(placeholder_games), "fixed": 0, "failed": 0}
        except EOFError:
            # Non-interactive mode, proceed automatically
            console.print(f"\n[blue]Non-interactive mode: proceeding to fix {len(placeholder_games)} games[/blue]")
        
        # Fix games
        console.print(f"\n[blue]Fixing {len(placeholder_games)} games...[/blue]")
        
        fixed = 0
        failed = 0
        
        for game in placeholder_games:
            if await self.fix_game_status(game, dry_run=False):
                fixed += 1
            else:
                failed += 1
        
        return {"total": len(placeholder_games), "fixed": fixed, "failed": failed}
    
    async def close(self):
        """Close the HTTP client."""
        # MissingTableClient doesn't need explicit closing
        pass


async def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Fix placeholder scores in Supabase database")
    parser.add_argument("--dry-run", action="store_true", default=True,
                       help="Show what would be changed without making changes (default)")
    parser.add_argument("--execute", action="store_true",
                       help="Actually execute the changes (overrides --dry-run)")
    parser.add_argument("--api-url", help="Override API base URL")
    parser.add_argument("--api-token", help="Override API token")
    
    args = parser.parse_args()
    
    # Load configuration
    try:
        config = load_config()
        api_url = args.api_url or config.missing_table_api_url
        api_token = args.api_token or config.missing_table_api_key
    except Exception as e:
        console.print(f"[red]Error loading configuration: {e}[/red]")
        console.print("[yellow]Please set MISSING_TABLE_API_BASE_URL and MISSING_TABLE_API_TOKEN environment variables[/yellow]")
        return 1
    
    # Determine if this is a dry run
    dry_run = not args.execute
    
    if dry_run:
        console.print("[yellow]Running in DRY RUN mode. Use --execute to make actual changes.[/yellow]")
    else:
        console.print("[red]EXECUTING CHANGES. This will modify your database![/red]")
    
    # Create fixer and run
    fixer = SupabaseDataFixer(api_url, api_token)
    
    try:
        results = await fixer.fix_all_placeholder_games(dry_run=dry_run)
        
        console.print(f"\n[blue]Summary:[/blue]")
        console.print(f"  Total games found: {results['total']}")
        console.print(f"  Successfully fixed: {results['fixed']}")
        console.print(f"  Failed: {results['failed']}")
        
        if dry_run and results['total'] > 0:
            console.print(f"\n[yellow]To execute these changes, run:[/yellow]")
            console.print(f"  python scripts/fix-supabase-data.py --execute")
        
        return 0 if results['failed'] == 0 else 1
        
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        return 1
    finally:
        await fixer.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
