"""
Feed values -> missing-table tournament fields. Pure and table-driven.

A tournament row carries three raw strings: a competition (``HD Group Play``),
a division (``A``, ``Playoffs``, ``FEST``) and a round label (``Round of 16``).
missing-table wants a round key from a fixed list and, for a real group, the
group label; it composes the stored group itself, so competition and group are
sent as the feed has them.

The tables were read off MLS NEXT Fest 2025 (modular11 event 75);
``tests/unit/fixtures/modular11_event_75/census.json`` holds every combination
seen there, and a test asserts each one still maps. A combination this module
does not know is reported, never guessed into a knockout round.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

# The round keys missing-table knows (docs/08-integrations/match-scraper.md in
# missing-table, "Tournament matches").
MT_ROUND_KEYS = frozenset(
    {
        "group_stage",
        "round_of_32",
        "round_of_16",
        "quarterfinal",
        "semifinal",
        "third_place",
        "final",
        "showcase",
        "consolation",
        "placement_final",
    }
)

# Round labels as the feed prints them. Longest first: the label is matched at
# the END of the text, and "Final" is the tail of longer labels.
KNOWN_LABELS: tuple[str, ...] = (
    "Final (Child Group of NEXT Pro)",
    "League (Pro Player Pathway)",
    "Round of 32",
    "Round of 16",
    "QuarterFinal",
    "Semi-Final",
    "Group Play",
    "Showcase",
    "Consolation",
    "Best Of",
    "Final",
)

# Anchored at the end, after a space or at the start: the feed sometimes
# prefixes the label with the venue's street address.
_LABEL_AT_END = re.compile(
    r"(?:^|\s)(" + "|".join(re.escape(label) for label in KNOWN_LABELS) + r")$"
)

KNOCKOUT_LABELS: dict[str, str] = {
    "Round of 32": "round_of_32",
    "Round of 16": "round_of_16",
    "QuarterFinal": "quarterfinal",
    "Semi-Final": "semifinal",
}

# Rounds where a source's bracket position, if it has one, is sent as the
# round order.
ROUND_ORDER_KEYS = frozenset(KNOCKOUT_LABELS.values()) | {"final"}

NEXT_PRO = "NEXT Pro"
# In 2025 the five NEXT Pro clubs played a round robin (division "NEXT Pro",
# label "Group Play") and its top two met in one match labelled this way, in
# division "Finals". That is a placing decided after group play — the same
# thing as the U13/U14 "Playoffs" final — and not the event's final: the
# knockout final has the same competition, and missing-table files both under
# it, so calling this one "final" would give the competition two.
NEXT_PRO_FINAL_LABEL = "Final (Child Group of NEXT Pro)"

# Divisions that are a real group. Anything else on the lists below is a stage
# name the feed puts in the division column.
_GROUP_DIVISION = re.compile(r"^[A-Z]{1,2}$")
_SINGLE_LETTER = re.compile(r"^[A-Z]$")
NOT_A_GROUP = frozenset({"FEST", "Playoff", "Playoffs", "Finals", "Consolation"})
PLACEMENT_DIVISIONS = frozenset({"Playoff", "Playoffs", "Finals"})

SHOWCASE_COMPETITIONS = frozenset({"Pro Player Pathway", "Best Of"})
SHOWCASE_LABELS = frozenset({"Showcase", "Best Of", "League (Pro Player Pathway)"})

# Competition prefix -> the league name this repo already sends for league
# matches (models.match_data.VALID_LEAGUES, assist_client.LEAGUE_FEEDS).
LEAGUE_BY_PREFIX: dict[str, str] = {"HD": "Homegrown", "AD": "Academy"}


class MappedRound(BaseModel):
    """What one row's competition, division and label come to."""

    label: str = Field(default="", description="The round label, cleaned")
    round_key: str | None = Field(default=None, description="missing-table round key")
    group: str | None = Field(
        default=None, description="Group label to send, if a group"
    )
    send_round_order: bool = Field(
        default=False,
        description="Whether a bracket position is sent as the round order",
    )
    unmapped: tuple[str, ...] = Field(
        default=(), description="Values this mapping does not know, for the summary"
    )


def collapse(value: str | None) -> str:
    """Trim, and squeeze runs of whitespace (non-breaking included) to one space."""
    return " ".join((value or "").replace("\xa0", " ").split())


def clean_round_label(raw: str | None) -> str:
    """The known label at the end of ``raw``, else ``raw`` with spaces collapsed.

    >>> clean_round_label("1200 E  Main St   Semi-Final")
    'Semi-Final'
    >>> clean_round_label("  Third  Place ")
    'Third Place'
    """
    text = collapse(raw)
    found = _LABEL_AT_END.search(text)
    return found.group(1) if found else text


def slugify(label: str) -> str:
    """A label as a round-key-shaped string (lowercase snake_case, max 40).

    Empty when the label has nothing a key can start with.
    """
    slug = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")[:40].strip("_")
    return slug if slug[:1].isalpha() else ""


def league_for(competition: str | None) -> str | None:
    """The league a competition belongs to, from its ``HD``/``AD`` first word."""
    words = collapse(competition).split(" ")
    return LEAGUE_BY_PREFIX.get(words[0]) if len(words) > 1 else None


def _round_without_label(competition: str, division: str) -> str | None:
    """Rules that need no label: what competition and division say alone."""
    if division == NEXT_PRO:
        return "group_stage"
    if division == "Consolation":
        return "consolation"
    if _SINGLE_LETTER.match(division):
        return "group_stage"
    if competition.endswith("Showcase"):
        return "showcase"
    if competition in SHOWCASE_COMPETITIONS:
        return "showcase"
    if competition.endswith("Group Play") and division in PLACEMENT_DIVISIONS:
        return "placement_final"
    return None


def _round_key(competition: str, division: str, label: str) -> str | None:
    """The round key, first rule that matches. None when nothing does."""
    if label == NEXT_PRO_FINAL_LABEL:
        return "placement_final"
    if division == NEXT_PRO:
        return "group_stage"
    if label in KNOCKOUT_LABELS:
        return KNOCKOUT_LABELS[label]
    if label == "Consolation" or division == "Consolation":
        return "consolation"
    if label == "Final":
        return "placement_final" if competition.endswith("Group Play") else "final"
    if label == "Group Play" or _SINGLE_LETTER.match(division):
        return "group_stage"
    if label in SHOWCASE_LABELS or competition.endswith("Showcase"):
        return "showcase"
    if competition in SHOWCASE_COMPETITIONS:
        return "showcase"
    return None


def map_round(
    competition: str | None, division: str | None, raw_label: str | None
) -> MappedRound:
    """Map one row. Never raises; what it does not know is in ``unmapped``."""
    comp = collapse(competition)
    div = collapse(division)
    label = clean_round_label(raw_label)
    unmapped: list[str] = []

    if not label:
        round_key = _round_without_label(comp, div)
        if round_key is None:
            # Never guess a knockout round: send none and say so.
            unmapped.append(f"no round: competition {comp!r}, division {div!r}")
    elif label in KNOWN_LABELS:
        round_key = _round_key(comp, div, label)
        if round_key is None:
            unmapped.append(
                f"no round: label {label!r}, competition {comp!r}, division {div!r}"
            )
    else:
        round_key = slugify(label) or None
        unmapped.append(f"label {label!r}")

    group: str | None = None
    if not comp:
        # missing-table namespaces a group by its competition. Without one,
        # group "A" of HD and group "A" of AD would be stored as the same
        # group, so no group is sent and the row is reported.
        unmapped.append(f"no competition: division {div!r}, label {label!r}")
    elif _GROUP_DIVISION.match(div) or div == NEXT_PRO:
        group = div
    elif div and div not in NOT_A_GROUP:
        unmapped.append(f"division {div!r}")
        if round_key == "group_stage":
            group = div

    return MappedRound(
        label=label,
        round_key=round_key,
        group=group,
        send_round_order=round_key in ROUND_ORDER_KEYS,
        unmapped=tuple(unmapped),
    )
