"""Division and conference ID lookup utilities.

This module provides functions to look up division IDs based on division
or conference names for queue message submission.
"""

from typing import Optional

# Division ID mappings from MLS Next website (Homegrown Division)
# These IDs match the values used in filter_application.py
DIVISION_ID_MAP = {
    "Central": 34,
    "Northeast": 41,
    "East": 35,
    "Mid-Atlantic": 68,
    "Florida": 46,
    "Southwest": 36,
    "Southeast": 37,
    "Northwest": 38,
    "Great Lakes": 39,
    "Texas": 40,
    "California": 42,
}

# Conference ID mappings (Academy Division)
# Conferences map to the same underlying division IDs
CONFERENCE_ID_MAP = {
    "New England": 41,  # Maps to Northeast
    "Northeast": 41,
    "Mid-Atlantic": 68,
    "Southeast": 37,
    "Florida": 46,
    "Central": 34,
    "Great Lakes": 39,
    "Texas": 40,
    "Southwest": 36,
    "Northwest": 38,
    "California": 42,
}


def get_division_id(division: str) -> Optional[int]:
    """
    Look up division ID by division name (Homegrown League).

    Args:
        division: Division name (e.g., "Northeast", "Central")

    Returns:
        Division ID (integer) or None if not found

    Example:
        >>> get_division_id("Northeast")
        41
        >>> get_division_id("Central")
        34
        >>> get_division_id("Unknown")
        None
    """
    if not division:
        return None
    return DIVISION_ID_MAP.get(division)


def get_conference_id(conference: str) -> Optional[int]:
    """
    Look up division ID by conference name (Academy League).

    Args:
        conference: Conference name (e.g., "New England", "Mid-Atlantic")

    Returns:
        Division ID (integer) or None if not found

    Example:
        >>> get_conference_id("New England")
        41
        >>> get_conference_id("Mid-Atlantic")
        68
        >>> get_conference_id("Unknown")
        None
    """
    if not conference:
        return None
    return CONFERENCE_ID_MAP.get(conference)


def get_division_id_for_league(
    league: str, division: Optional[str], conference: Optional[str]
) -> Optional[int]:
    """
    Get division ID based on league type.

    This is the main function to use when submitting matches to the queue.
    It automatically selects the correct lookup based on league type:
    - Homegrown: uses division name
    - Academy: uses conference name

    Args:
        league: League type ("Homegrown" or "Academy")
        division: Division name (for Homegrown)
        conference: Conference name (for Academy)

    Returns:
        Division ID (integer) or None if not found

    Example:
        >>> # Homegrown league
        >>> get_division_id_for_league("Homegrown", "Northeast", None)
        41

        >>> # Academy league
        >>> get_division_id_for_league("Academy", None, "New England")
        41

        >>> # Academy league can also accept division if conference is missing
        >>> get_division_id_for_league("Academy", "Northeast", None)
        41
    """
    if league == "Academy":
        # Academy league uses conference
        if conference:
            return get_conference_id(conference)
        # Fallback to division if conference not provided
        if division:
            return get_division_id(division)
    elif league == "Homegrown":
        # Homegrown league uses division
        if division:
            return get_division_id(division)

    return None


def get_all_divisions() -> dict[str, int]:
    """
    Get all division name to ID mappings.

    Returns:
        Dictionary of division name -> division ID

    Example:
        >>> divisions = get_all_divisions()
        >>> divisions["Northeast"]
        41
    """
    return DIVISION_ID_MAP.copy()


def get_all_conferences() -> dict[str, int]:
    """
    Get all conference name to ID mappings.

    Returns:
        Dictionary of conference name -> division ID

    Example:
        >>> conferences = get_all_conferences()
        >>> conferences["New England"]
        41
    """
    return CONFERENCE_ID_MAP.copy()
