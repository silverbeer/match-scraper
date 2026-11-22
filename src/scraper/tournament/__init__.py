"""Tournament event scraping: swappable sources, one mapping, one message.

A tournament (MLS NEXT Fest) is published either as a modular11 event or on
the assist feeds, and which one is not known until the schedule appears. Each
is a :class:`~.base.TournamentSource` returning the same source-agnostic
``TournamentMatch`` rows; :mod:`.mapping` turns a row's raw competition,
division and round label into missing-table's round key.

Nothing is imported here on purpose: ``src.models.tournament`` imports
:mod:`.mapping`, and the sources import ``src.models.tournament``.
"""
