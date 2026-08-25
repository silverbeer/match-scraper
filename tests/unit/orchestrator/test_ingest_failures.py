"""Reading missing-table's unresolved names at end of run (SB-831).

This call runs after the matches are already submitted. Its defining property
is that it can only ever ADD information to the report: any failure degrades
to an empty list, which is exactly what the report said before this existed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.orchestrator.ingest_failures import fetch_ingest_failures

ROWS = [
    {
        "raw_name": "Intercontinental Football Academy of New England",
        "kind": "team",
        "match_count": 88,
    },
    {"raw_name": "Turnpike", "kind": "division", "match_count": 3},
]
SINCE = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)


def _response(json_data=None, raise_for_status=None):
    resp = MagicMock()
    resp.json.return_value = json_data if json_data is not None else {"failures": []}
    if raise_for_status:
        resp.raise_for_status.side_effect = raise_for_status
    return resp


class TestFetch:
    def test_returns_the_rows(self) -> None:
        with patch("httpx.get", return_value=_response({"failures": ROWS})):
            assert fetch_ingest_failures("http://mt", "token") == ROWS

    def test_authenticates_as_a_service_account(self) -> None:
        # The endpoint accepts service accounts precisely so this call can be
        # made; without the header it is a 401 and a silently empty section.
        with patch("httpx.get", return_value=_response()) as get:
            fetch_ingest_failures("http://mt", "sa-token")
        assert get.call_args.kwargs["headers"]["Authorization"] == "Bearer sa-token"

    def test_windows_the_query_to_this_run(self) -> None:
        # Without `since` the report would carry every name that has ever
        # failed rather than what this run cost.
        with patch("httpx.get", return_value=_response()) as get:
            fetch_ingest_failures("http://mt", "token", since=SINCE)
        assert get.call_args.kwargs["params"]["since"] == SINCE.isoformat()

    def test_no_since_asks_for_everything_open(self) -> None:
        with patch("httpx.get", return_value=_response()) as get:
            fetch_ingest_failures("http://mt", "token")
        assert "since" not in get.call_args.kwargs["params"]

    def test_hits_the_admin_endpoint(self) -> None:
        with patch("httpx.get", return_value=_response()) as get:
            fetch_ingest_failures("http://mt", "token")
        assert get.call_args.args[0] == "http://mt/api/admin/ingest-failures"


class TestFailureIsAlwaysEmptyNeverFatal:
    def test_no_api_key_skips_the_call_entirely(self) -> None:
        with patch("httpx.get") as get:
            assert fetch_ingest_failures("http://mt", "") == []
        get.assert_not_called()

    @pytest.mark.parametrize(
        "error",
        [
            httpx.ConnectError("refused"),
            httpx.ReadTimeout("slow"),
            RuntimeError("something else"),
        ],
    )
    def test_a_transport_error_degrades_to_empty(self, error) -> None:
        with patch("httpx.get", side_effect=error):
            assert fetch_ingest_failures("http://mt", "token") == []

    def test_an_http_error_degrades_to_empty(self) -> None:
        resp = _response(
            raise_for_status=httpx.HTTPStatusError(
                "403", request=MagicMock(), response=MagicMock()
            )
        )
        with patch("httpx.get", return_value=resp):
            assert fetch_ingest_failures("http://mt", "token") == []

    def test_an_unexpected_body_degrades_to_empty(self) -> None:
        with patch("httpx.get", return_value=_response({"unexpected": True})):
            assert fetch_ingest_failures("http://mt", "token") == []
