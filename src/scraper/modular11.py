"""
Site-side constants and helpers for the modular11 backend behind MLS Next.

The MLS Next schedule page (``mlssoccer.com/mlsnext/schedule/all/``) embeds a
modular11 iframe whose filters are driven by numeric IDs. Those same IDs drive
the ``public_schedule/league/get_matches`` HTTP endpoint, which returns the
fixture list as an HTML fragment without any browser automation.

Two ID spaces are easy to confuse and are deliberately kept apart:

* **modular11 group IDs** (this module) describe the *website* and change when
  MLS Next reorganises its divisions between seasons.
* **missing-table division IDs** (``src.utils.division_lookup``) describe our
  own database and must stay stable regardless of what the website does.

They currently agree for the divisions we scrape, but they are not the same
thing and must not be edited as if they were.
"""

from __future__ import annotations

from datetime import date

# MLS NEXT tournament ID on modular11. Stable across the seasons observed so far.
TOURNAMENT_ID = "12"

# Age group → modular11 ``age[]`` value. Verified unchanged for 2026-2027.
AGE_GROUP_IDS: dict[str, str] = {
    "U13": "21",
    "U14": "22",
    "U15": "33",
    "U16": "14",
    "U17": "15",
    "U19": "26",
}

# Division name → modular11 ``groups[]`` value, read from the live
# ``select[js-groups]`` on 2026-08-02 for the 2026-2027 season.
#
# NOTE: several IDs changed from the 2025-2026 season — Southeast 37→45,
# Southwest 36→52, Northwest 38→57 — and Great Lakes, Texas and California no
# longer exist as groups. The divisions we scrape (Northeast, Florida,
# Mid-Atlantic) are unchanged. Do not copy these values into
# ``division_lookup.DIVISION_ID_MAP``; that map addresses missing-table, not
# modular11.
DIVISION_GROUP_IDS: dict[str, str] = {
    "Central": "34",
    "East": "35",
    "Florida": "46",
    "Frontier": "66",
    "Mid-America": "67",
    "Mid-Atlantic": "68",
    "MLS Academy": "225",
    "Northeast": "41",
    "Northwest": "57",
    "Southeast": "45",
    "Southwest": "52",
    "West": "33",
}

# Divisions prioritised for the 2026-2027 fall segment.
PRIORITY_DIVISIONS: tuple[str, ...] = ("Northeast", "Florida", "Mid-Atlantic")

# Age groups in priority order — U15 first, per SB-499.
PRIORITY_AGE_GROUPS: tuple[str, ...] = ("U15", "U13", "U14", "U16", "U17", "U19")

# The season runs August → mid-July. These bounds mirror the default
# ``start_date``/``end_date`` the modular11 iframe sends for itself.
SEASON_START_MONTH = 8
SEASON_START_DAY = 1
SEASON_END_MONTH = 7
SEASON_END_DAY = 15


def current_season_year(today: date | None = None) -> int:
    """
    Return the starting year of the season containing ``today``.

    August or later belongs to the season starting that year; January through
    July belongs to the season that started the previous year.

    >>> current_season_year(date(2026, 8, 2))
    2026
    >>> current_season_year(date(2027, 3, 1))
    2026
    """
    today = today or date.today()
    return today.year if today.month >= SEASON_START_MONTH else today.year - 1


def season_label(season_year: int) -> str:
    """
    Return the missing-table season identifier for a season start year.

    >>> season_label(2026)
    '2026-2027'
    """
    return f"{season_year}-{season_year + 1}"


def current_season_label(today: date | None = None) -> str:
    """Return the season identifier covering ``today``, e.g. ``'2026-2027'``."""
    return season_label(current_season_year(today))


def season_window(season_year: int) -> tuple[date, date]:
    """
    Return the ``(start, end)`` dates bounding a season.

    >>> season_window(2026)
    (datetime.date(2026, 8, 1), datetime.date(2027, 7, 15))
    """
    return (
        date(season_year, SEASON_START_MONTH, SEASON_START_DAY),
        date(season_year + 1, SEASON_END_MONTH, SEASON_END_DAY),
    )


def fall_segment_window(season_year: int) -> tuple[date, date]:
    """
    Return the ``(start, end)`` dates bounding a season's fall segment.

    The fall segment runs from the season start through the end of the calendar
    year; the spring segment picks up in January.
    """
    return (
        date(season_year, SEASON_START_MONTH, SEASON_START_DAY),
        date(season_year, 12, 31),
    )
