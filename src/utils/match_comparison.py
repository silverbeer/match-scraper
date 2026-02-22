"""
Match comparison utility for detecting changes between scraping runs.

Handles loading previous match state, comparing matches, and generating diffs.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from src.utils.logger import get_logger

logger = get_logger()


class MatchComparison:
    """Utility for comparing matches and detecting changes."""

    def __init__(self, state_file_path: Path):
        """
        Initialize match comparison utility.

        Args:
            state_file_path: Path to the state file for storing previous matches
        """
        self.state_file_path = state_file_path
        self._previous_matches: dict[str, dict[str, Any]] = {}

    def load_previous_state(self) -> dict[str, dict[str, Any]]:
        """
        Load previous match state from state file.

        Returns:
            Dictionary mapping match IDs to match data
        """
        if not self.state_file_path.exists():
            logger.info("No previous state file found, starting fresh")
            return {}

        try:
            with open(self.state_file_path) as f:
                state = json.load(f)
                self._previous_matches = state.get("matches", {})
                logger.info(
                    "Loaded previous state",
                    extra={
                        "previous_match_count": len(self._previous_matches),
                        "last_run_id": state.get("last_run_id"),
                    },
                )
                return self._previous_matches
        except Exception as e:
            logger.error(
                f"Failed to load previous state: {e}",
                extra={"error": str(e), "state_file": str(self.state_file_path)},
            )
            return {}

    def save_current_state(
        self, run_id: str, matches: dict[str, dict[str, Any]]
    ) -> None:
        """
        Save current match state to state file.

        Args:
            run_id: Current run ID
            matches: Dictionary mapping match IDs to match data
        """
        state = {
            "last_run_id": run_id,
            "last_run_timestamp": datetime.utcnow().isoformat(),
            "matches": matches,
        }

        try:
            with open(self.state_file_path, "w") as f:
                json.dump(state, f, indent=2, default=str)
            logger.info(
                "Saved current state",
                extra={"match_count": len(matches), "run_id": run_id},
            )
        except Exception as e:
            logger.error(
                f"Failed to save current state: {e}",
                extra={"error": str(e), "state_file": str(self.state_file_path)},
            )

    def compare_match(
        self, match_id: str, current_match: dict[str, Any]
    ) -> tuple[str, dict[str, dict[str, Any]] | None]:
        """
        Compare a match against previous state.

        Args:
            match_id: External match ID
            current_match: Current match data

        Returns:
            Tuple of (status, changes) where status is "discovered", "updated", or "unchanged"
            and changes is a dict of field-level diffs (only for "updated")
        """
        if match_id not in self._previous_matches:
            return "discovered", None

        previous_match = self._previous_matches[match_id]
        changes = self._generate_changes(previous_match, current_match)

        if changes:
            return "updated", changes
        else:
            return "unchanged", None

    def _generate_changes(
        self, previous: dict[str, Any], current: dict[str, Any]
    ) -> dict[str, dict[str, Any]]:
        """
        Generate field-level diff between previous and current match data.

        Args:
            previous: Previous match data
            current: Current match data

        Returns:
            Dictionary mapping field names to {"from": old_value, "to": new_value}
        """
        changes = {}

        # Compare all fields in current match
        for field, current_value in current.items():
            previous_value = previous.get(field)

            # Skip if values are the same
            if current_value == previous_value:
                continue

            # Special handling for None/null comparisons
            if previous_value is None and current_value is None:
                continue

            changes[field] = {"from": previous_value, "to": current_value}

        # Check for removed fields (in previous but not in current)
        for field in previous.keys():
            if field not in current:
                changes[field] = {"from": previous[field], "to": None}

        return changes

    def batch_compare_matches(
        self, current_matches: list[dict[str, Any]]
    ) -> dict[str, list[dict[str, Any]]]:
        """
        Compare a batch of matches and categorize them.

        Args:
            current_matches: List of current match data dictionaries

        Returns:
            Dictionary with keys: "discovered", "updated", "unchanged"
            Each value is a list of match data with added "changes" field for updates
        """
        categorized: dict[str, list[dict[str, Any]]] = {
            "discovered": [],
            "updated": [],
            "unchanged": [],
        }

        for match in current_matches:
            match_id = match.get("external_match_id")
            if not match_id:
                logger.warning(
                    "Match missing external_match_id, skipping comparison",
                    extra={"match": match},
                )
                continue

            status, changes = self.compare_match(match_id, match)

            if status == "updated" and changes:
                match_with_changes = match.copy()
                match_with_changes["_changes"] = changes
                categorized["updated"].append(match_with_changes)
            else:
                categorized[status].append(match)

        logger.info(
            "Match comparison complete",
            extra={
                "discovered": len(categorized["discovered"]),
                "updated": len(categorized["updated"]),
                "unchanged": len(categorized["unchanged"]),
            },
        )

        return categorized

    def build_state_from_matches(
        self, matches: list[dict[str, Any]]
    ) -> dict[str, dict[str, Any]]:
        """
        Build a state dictionary from a list of matches.

        Args:
            matches: List of match data dictionaries

        Returns:
            Dictionary mapping match IDs to match data
        """
        state = {}
        for match in matches:
            match_id = match.get("external_match_id")
            if match_id:
                # Remove internal fields like _changes before saving
                clean_match = {k: v for k, v in match.items() if not k.startswith("_")}
                state[match_id] = clean_match
        return state
