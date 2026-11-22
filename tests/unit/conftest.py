"""Fixtures shared by the unit tests."""

import socket

import pytest


@pytest.fixture
def no_network(monkeypatch):
    """Fail the test if anything opens a real connection.

    Opt-in (``pytestmark = pytest.mark.usefixtures("no_network")``) rather
    than suite-wide: it is used by the tournament and scrape-event modules,
    whose safety otherwise rests on every test remembering to pass a fake
    source. ``httpx.MockTransport`` never reaches a socket, so mocked tests
    are unaffected.
    """

    def refuse(self, address, *args, **kwargs):
        raise AssertionError(f"test tried to open a network connection to {address!r}")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
