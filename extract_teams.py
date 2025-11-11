#!/usr/bin/env python3
"""
Extract teams from clubs.json for a specific age group, league, and conference.

Usage:
    python extract_teams.py --age-group U14 --league Academy --conference "New England" --output teams.json
"""

import json
import sys
from pathlib import Path
from typing import Optional


def extract_teams(
    clubs_file: str,
    age_group: str,
    league: str,
    conference: Optional[str] = None,
    division: Optional[str] = None,
    output_file: str = "teams.json",
) -> None:
    """Extract teams from clubs.json based on filters.

    Args:
        clubs_file: Path to clubs.json file
        age_group: Age group to filter (e.g., "U14")
        league: League to filter ("Homegrown" or "Academy")
        conference: Conference to filter (for Academy league)
        division: Division to filter (for Homegrown league)
        output_file: Output JSON file path
    """
    # Load clubs data
    with open(clubs_file, "r") as f:
        clubs = json.load(f)

    # Extract matching teams
    matching_teams = []

    for club in clubs:
        club_name = club.get("club_name", "")
        location = club.get("location", "")
        website = club.get("website", "")

        for team in club.get("teams", []):
            team_league = team.get("league", "")
            team_division = team.get("division")
            team_conference = team.get("conference")
            age_groups = team.get("age_groups", [])

            # Check if team matches filters
            if team_league != league:
                continue

            if age_group not in age_groups:
                continue

            # Check conference/division based on league type
            if league == "Academy" and conference:
                if team_conference != conference:
                    continue
            elif league == "Homegrown" and division:
                if team_division != division:
                    continue

            # Add team to results
            team_data = {
                "team_name": team.get("team_name", ""),
                "club_name": club_name,
                "location": location,
                "website": website,
                "league": team_league,
                "age_group": age_group,
            }

            if league == "Academy":
                team_data["conference"] = team_conference
            else:
                team_data["division"] = team_division

            matching_teams.append(team_data)

    # Create output data structure
    output_data = {
        "metadata": {
            "age_group": age_group,
            "league": league,
            "conference": conference if league == "Academy" else None,
            "division": division if league == "Homegrown" else None,
            "total_teams": len(matching_teams),
            "extracted_from": clubs_file,
        },
        "teams": sorted(matching_teams, key=lambda x: x["team_name"]),
    }

    # Write to output file
    with open(output_file, "w") as f:
        json.dump(output_data, f, indent=2)

    print(f"Extracted {len(matching_teams)} teams to {output_file}")

    # Print team list
    print("\nTeams found:")
    for i, team in enumerate(output_data["teams"], 1):
        print(f"{i}. {team['team_name']}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Extract teams from clubs.json")
    parser.add_argument(
        "--clubs-file",
        default="clubs.json",
        help="Path to clubs.json file (default: clubs.json)",
    )
    parser.add_argument(
        "--age-group",
        required=True,
        help="Age group to filter (e.g., U14)",
    )
    parser.add_argument(
        "--league",
        required=True,
        choices=["Homegrown", "Academy"],
        help="League to filter",
    )
    parser.add_argument(
        "--conference",
        help="Conference to filter (for Academy league)",
    )
    parser.add_argument(
        "--division",
        help="Division to filter (for Homegrown league)",
    )
    parser.add_argument(
        "--output",
        default="teams.json",
        help="Output JSON file path (default: teams.json)",
    )

    args = parser.parse_args()

    # Validate arguments
    if args.league == "Academy" and not args.conference:
        print("Error: --conference is required for Academy league")
        sys.exit(1)
    elif args.league == "Homegrown" and not args.division:
        print("Error: --division is required for Homegrown league")
        sys.exit(1)

    # Run extraction
    extract_teams(
        clubs_file=args.clubs_file,
        age_group=args.age_group,
        league=args.league,
        conference=args.conference,
        division=args.division,
        output_file=args.output,
    )
