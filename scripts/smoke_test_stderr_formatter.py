#!/usr/bin/env python3
"""
Smoke test for StderrExtraFormatter.

The Problem:
    In K8s, the stderr handler (kubectl logs) used to drop all extra= fields.
    You'd see "Element not found within timeout" with zero context.

The Fix:
    StderrExtraFormatter appends extra fields as [key=value ...] after the message.

What This Script Does:
    Wires up the exact same formatter + format string used by the K8s stderr handler,
    then fires log messages through it so you can eyeball the output. Each test
    explains what it's verifying and shows a BEFORE (old behavior) vs AFTER (new).

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
    print()
    print("  This is the formatter used by the K8s stderr handler (kubectl logs).")
    print("  Previously it used logging.Formatter which dropped all extra= fields.")
    print("  StderrExtraFormatter appends them as [key=value ...] after the message.")
    print(f"  Values longer than {_EXTRA_VALUE_MAX_LEN} chars are truncated with '...'")
    print(SEPARATOR)

    # --- Test 1 ---
    print()
    print("[TEST 1] Do extra fields show up at all?")
    print("  The whole point of this change. Pass selector, state, and timeout")
    print("  as extra= fields — they should appear in brackets after the message.")
    print()
    print("  BEFORE:  WARNING - Element not found within timeout")
    print("  AFTER:   ", end="", flush=True)
    logger.warning(
        "Element not found within timeout",
        extra={"selector": ".container-fluid", "state": "visible", "timeout": 5000},
    )

    # --- Test 2 ---
    print()
    print("[TEST 2] No extra fields — does it stay clean?")
    print("  A log call with no extra= should produce no brackets, no trailing junk.")
    print()
    print("  BEFORE:  WARNING - Something happened")
    print("  AFTER:   ", end="", flush=True)
    logger.warning("Something happened")

    # --- Test 3 ---
    long_url = "https://www.mlssoccer.com/mlsnext/schedule/" + "a" * 200
    print()
    print(f"[TEST 3] Long values get truncated (>{_EXTRA_VALUE_MAX_LEN} chars)")
    print(f"  Passing a {len(long_url)}-char URL. It should be cut to")
    print(
        f"  {_EXTRA_VALUE_MAX_LEN} chars and end with '...' so stderr stays readable."
    )
    print()
    print("  AFTER:   ", end="", flush=True)
    logger.warning("Navigation timeout", extra={"url": long_url, "attempt": 2})

    # --- Test 4 ---
    print()
    print("[TEST 4] Works across all log levels")
    print(
        "  Extras should appear regardless of whether it's ERROR, WARNING, INFO, or DEBUG."
    )
    print()
    for level, component in [
        (logging.ERROR, "browser"),
        (logging.WARNING, "parser"),
        (logging.INFO, "scheduler"),
        (logging.DEBUG, "cache"),
    ]:
        print("  AFTER:   ", end="", flush=True)
        logger.log(
            level,
            f"{logging.getLevelName(level)} from {component}",
            extra={"component": component},
        )

    # --- Test 5 ---
    print()
    print("[TEST 5] Realistic scraper messages")
    print("  These are actual log patterns from the scraper codebase.")
    print("  This is what kubectl logs will look like after deploying.")
    print()
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
        print("  AFTER:   ", end="", flush=True)
        logger.warning(msg, extra=extras)

    print()
    print(SEPARATOR)
    print("DONE — if AFTER lines have [key=value ...] context, the formatter works.")
    print(SEPARATOR)


if __name__ == "__main__":
    main()
