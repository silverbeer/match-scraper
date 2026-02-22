#!/usr/bin/env python3
"""
Smoke test for StderrExtraFormatter.

Verifies that the stderr log handler (used by kubectl logs in K8s) correctly
appends user-supplied extra fields as [key=value ...] after the log message.

This simulates exactly what the K8s stderr handler does — same formatter class,
same format string — but writes to stderr locally so you can eyeball the output.

Run:
    cd /path/to/match-scraper
    uv run python scripts/smoke_test_stderr_formatter.py
"""

import logging
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.utils.logger import _EXTRA_VALUE_MAX_LEN, StderrExtraFormatter  # noqa: E402

SEPARATOR = "-" * 72


def setup_test_logger() -> logging.Logger:
    """Create a logger with StderrExtraFormatter, matching the K8s stderr handler config."""
    logger = logging.getLogger("smoke-test-stderr-formatter")
    logger.handlers.clear()
    logger.setLevel(logging.DEBUG)

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(StderrExtraFormatter("%(levelname)s - %(message)s"))
    logger.addHandler(handler)
    return logger


def main() -> None:
    logger = setup_test_logger()

    print(SEPARATOR)
    print("SMOKE TEST: StderrExtraFormatter")
    print(f"  Formatter class: {StderrExtraFormatter.__name__}")
    print("  Format string:   %(levelname)s - %(message)s")
    print(f"  Truncation:      {_EXTRA_VALUE_MAX_LEN} chars per value")
    print("  Output target:   stderr (same as kubectl logs handler)")
    print(SEPARATOR)

    # --- Test 1: Multiple extra fields ---
    print("\n[TEST 1] Multiple extra fields")
    print("  Calling: logger.warning('Element not found within timeout',")
    print(
        "             extra={'selector': '.container-fluid', 'state': 'visible', 'timeout': 5000})"
    )
    print(
        "  Expect:  WARNING - Element not found within timeout [selector=... state=... timeout=...]"
    )
    print("  Output:  ", end="", flush=True)
    logger.warning(
        "Element not found within timeout",
        extra={"selector": ".container-fluid", "state": "visible", "timeout": 5000},
    )

    # --- Test 2: Single extra field ---
    print("\n[TEST 2] Single extra field")
    print("  Calling: logger.warning('Invalid age group', extra={'age_group': 'U14'})")
    print("  Expect:  WARNING - Invalid age group [age_group=U14]")
    print("  Output:  ", end="", flush=True)
    logger.warning("Invalid age group", extra={"age_group": "U14"})

    # --- Test 3: Long value gets truncated ---
    long_url = "https://www.mlssoccer.com/mlsnext/schedule/" + "a" * 200
    print(f"\n[TEST 3] Long value truncation (>{_EXTRA_VALUE_MAX_LEN} chars)")
    print(
        f"  Calling: logger.warning('Navigation timeout', extra={{'url': '<{len(long_url)} char URL>', 'attempt': 2}})"
    )
    print(f"  Expect:  URL truncated to {_EXTRA_VALUE_MAX_LEN} chars ending with '...'")
    print("  Output:  ", end="", flush=True)
    logger.warning("Navigation timeout", extra={"url": long_url, "attempt": 2})

    # --- Test 4: No extra fields ---
    print("\n[TEST 4] No extra fields (no brackets)")
    print("  Calling: logger.warning('Something happened')")
    print("  Expect:  WARNING - Something happened")
    print("  Output:  ", end="", flush=True)
    logger.warning("Something happened")

    # --- Test 5: Different log levels ---
    print("\n[TEST 5] Different log levels with extras")
    print(
        "  Calling: ERROR, WARNING, INFO, DEBUG — each with extra={'component': '...'}"
    )
    for level, component in [
        (logging.ERROR, "browser"),
        (logging.WARNING, "parser"),
        (logging.INFO, "scheduler"),
        (logging.DEBUG, "cache"),
    ]:
        print("  Output:  ", end="", flush=True)
        logger.log(
            level,
            f"{logging.getLevelName(level)} from {component}",
            extra={"component": component},
        )

    # --- Test 6: Realistic scraper log lines ---
    print(
        "\n[TEST 6] Realistic scraper messages (what kubectl logs will actually show)"
    )
    realistic = [
        (
            "Retry after transient error",
            {"error_type": "TimeoutError", "attempt": 2, "max_retries": 3},
        ),
        (
            "Match row missing score column",
            {"age_group": "U14", "division": "Northeast", "row_index": 7},
        ),
        (
            "Page navigation complete",
            {
                "url": "https://www.mlssoccer.com/mlsnext/schedule/?month=2026-02",
                "load_time_ms": 1820,
            },
        ),
        (
            "Submitting matches to queue",
            {"match_count": 12, "queue": "match-submissions", "dry_run": False},
        ),
    ]
    for msg, extras in realistic:
        print("  Output:  ", end="", flush=True)
        logger.warning(msg, extra=extras)

    print(f"\n{SEPARATOR}")
    print("SMOKE TEST COMPLETE — review output above")
    print(SEPARATOR)


if __name__ == "__main__":
    main()
