"""Read missing-table's unresolved ingest names at the end of a run (SB-831).

Publishing to RabbitMQ is not the same as missing-table accepting the match.
Team and division resolution happens later, in a Celery worker in another
repository, so `_submission_errors` — which records publish failures — is
silent about the most common way a run fails.

That silence is not neutral: it reads as success. A run where every name was
unknown reported "1432 found, 1432 submitted, 0 errors" while nothing landed.

missing-table records those failures in `ingest_failures` (SB-829) and exposes
them here. Folding them into the run report is what makes a green report mean
green.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import structlog

logger = structlog.get_logger()

# Short: this runs after the work is done, and a slow API must not be the
# reason a report never arrives.
TIMEOUT_SECONDS = 15.0


def fetch_ingest_failures(
    api_url: str,
    api_key: str,
    since: datetime | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Return missing-table's open unresolved names, newest first.

    Args:
        api_url: missing-table API base URL.
        api_key: Service-account token. The endpoint accepts service accounts
            precisely so this call can be made.
        since: Only names seen since this moment — normally the start of the
            run, so the report describes what THIS run cost rather than every
            name that has ever been wrong.
        limit: Maximum rows to request.

    Returns an empty list on any failure. This is a reporting enrichment
    running after the matches are already submitted; it must never be the
    reason a run is marked failed, and an empty list degrades the report to
    exactly what it said before this existed.
    """
    import httpx

    if not api_key:
        logger.debug("ingest_failures.skipped", reason="no api key")
        return []

    params: dict[str, Any] = {"limit": limit}
    if since is not None:
        params["since"] = since.isoformat()

    url = f"{api_url}/api/admin/ingest-failures"
    try:
        resp = httpx.get(
            url,
            params=params,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        failures = resp.json().get("failures", [])
    except Exception as exc:
        logger.warning("ingest_failures.fetch_failed", error=str(exc))
        return []

    if failures:
        logger.info(
            "ingest_failures.found",
            names=len(failures),
            matches=sum(f.get("match_count", 0) for f in failures),
        )
    return failures
