"""The contract every tournament source meets."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Protocol

from ...models.tournament import TournamentMatch


class TournamentSource(Protocol):
    """Where a tournament's matches are read from.

    A source only reads and reports what the feed says: raw team names, raw
    competition, division and round label. Turning those into a missing-table
    message is ``TournamentMatch.to_message``, the same for every source, so
    swapping the source cannot change what is sent.
    """

    #: Short name, as accepted by ``scrape-event --source``.
    name: str
    #: Prepended to a row's source id to make ``external_match_id``.
    id_prefix: str
    #: Age group -> why it could not be read. The other age groups still are.
    failures: dict[str, str]
    #: Feed values the source could not interpret -> how many rows carried it.
    unmapped: dict[str, int]

    async def fetch(
        self, age_groups: Sequence[str], start: date, end: date
    ) -> list[TournamentMatch]:
        """Every match of the event for ``age_groups`` dated ``start``..``end``."""
        ...
