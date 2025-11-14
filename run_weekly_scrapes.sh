#!/bin/bash
# Run weekly scrapes from Sep 1 to Nov 10, 2025
# Academy League, U14, New England Conference

set -e

echo "Starting weekly scrapes from 2025-09-01 to 2025-11-10"
echo "League: Academy | Age Group: U14 | Conference: New England"
echo ""

# Define all weeks
weeks=(
    "2025-09-01:2025-09-08"
    "2025-09-08:2025-09-15"
    "2025-09-15:2025-09-22"
    "2025-09-22:2025-09-29"
    "2025-09-29:2025-10-06"
    "2025-10-06:2025-10-13"
    "2025-10-13:2025-10-20"
    "2025-10-20:2025-10-27"
    "2025-10-27:2025-11-03"
    "2025-11-03:2025-11-10"
)

week_num=1
for week in "${weeks[@]}"; do
    from_date="${week%:*}"
    to_date="${week#*:}"

    echo "=========================================="
    echo "Week $week_num: $from_date to $to_date"
    echo "=========================================="

    uv run python -m src.cli.main scrape \
        --league Academy \
        --age-group U14 \
        --conference "New England" \
        --from "$from_date" \
        --to "$to_date" \
        --submit-queue

    exit_code=$?
    if [ $exit_code -ne 0 ]; then
        echo "ERROR: Week $week_num failed with exit code $exit_code"
        exit $exit_code
    fi

    echo "✓ Week $week_num completed successfully"
    echo ""

    ((week_num++))
done

echo "=========================================="
echo "All 10 weeks completed successfully!"
echo "=========================================="
