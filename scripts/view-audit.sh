#!/bin/bash
# Audit log viewer - Easy way to query match audit logs with jq

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Default to today's audit file
AUDIT_DIR="./audit"
DATE=${DATE:-$(date +%Y-%m-%d)}
AUDIT_FILE="${AUDIT_DIR}/match-audit-${DATE}.jsonl"

# Usage information
usage() {
    cat << EOF
${BLUE}Audit Log Viewer${NC}

Usage: $0 [command] [options]

Commands:
    all                     Show all matches
    team <name>            Show matches for a specific team
    league <name>          Show matches for a specific league (Homegrown/Academy)
    date <YYYY-MM-DD>      Show matches for a specific date
    stats                  Show statistics summary
    changes                Show only matches that were updated
    errors                 Show queue submission errors
    runs                   Show all scraping runs
    tail [options]         Show recent audit events (tail mode)
    raw                    Show raw JSON for all events

Tail Options:
    -f, --follow           Follow mode: continuously watch for new events
    -n <number>            Number of recent lines to show (default: 20)
    -t <type>              Filter by event type:
                            match    - Match events (discovered/updated)
                            error    - Queue errors
                            run      - Run start/complete events
                            queue    - Queue submission events
                            all      - All events (default)

Options:
    DATE=YYYY-MM-DD        Set date (default: today)

Examples:
    $0 team "Rochester NY FC"
    $0 league Academy
    DATE=2025-11-12 $0 all
    $0 stats
    $0 changes
    $0 tail -n 30              # Show last 30 events
    $0 tail -f                 # Follow mode (live updates)
    $0 tail -f -t match        # Follow only match events
    $0 tail -f -t error        # Monitor for errors

EOF
    exit 1
}

# Check if audit file exists
check_file() {
    if [ ! -f "$AUDIT_FILE" ]; then
        echo -e "${RED}Error: Audit file not found: $AUDIT_FILE${NC}"
        echo -e "Available files:"
        ls -1 ${AUDIT_DIR}/match-audit-*.jsonl 2>/dev/null || echo "  No audit files found"
        exit 1
    fi
}

# Show all matches
show_all() {
    check_file
    echo -e "${BLUE}=== All Matches - $DATE ===${NC}\n"

    cat "$AUDIT_FILE" | \
    jq -r 'select(.event_type == "match_discovered" or .event_type == "match_updated") |
           "\(.match_data.match_date) | \(.match_data.external_match_id) | \(.match_data.home_team) vs \(.match_data.away_team) | \(.match_data.home_score // "?")-\(.match_data.away_score // "?") | \(.match_data.match_status)"' | \
    sort | \
    awk -F'|' '{printf "%-12s %-8s %-50s %s\n", $1, $2, $3, $4}'
}

# Show matches for a specific team
show_team() {
    local team="$1"
    if [ -z "$team" ]; then
        echo -e "${RED}Error: Team name required${NC}"
        echo "Usage: $0 team \"Team Name\""
        exit 1
    fi

    check_file
    echo -e "${BLUE}=== Matches for: $team - $DATE ===${NC}\n"

    grep -i "$team" "$AUDIT_FILE" | \
    jq -r 'select(.match_data != null) |
           "\(.match_data.match_date) | #\(.match_data.external_match_id) | \(.match_data.home_team) vs \(.match_data.away_team) | Score: \(.match_data.home_score // "?")-\(.match_data.away_score // "?") | \(.match_data.match_status) | \(.match_data.location // "Unknown location")"'

    echo -e "\n${GREEN}Total matches: $(grep -i "$team" "$AUDIT_FILE" | jq -r 'select(.match_data != null)' | wc -l | tr -d ' ')${NC}"
}

# Show matches for a specific league
show_league() {
    local league="$1"
    if [ -z "$league" ]; then
        echo -e "${RED}Error: League name required${NC}"
        echo "Usage: $0 league [Homegrown|Academy]"
        exit 1
    fi

    check_file
    echo -e "${BLUE}=== $league League Matches - $DATE ===${NC}\n"

    cat "$AUDIT_FILE" | \
    jq -r --arg league "$league" 'select(.match_data != null and .match_data.league == $league) |
           "\(.match_data.match_date) | #\(.match_data.external_match_id) | \(.match_data.home_team) vs \(.match_data.away_team) | \(.match_data.home_score // "?")-\(.match_data.away_score // "?") | \(.match_data.match_status)"' | \
    sort

    echo -e "\n${GREEN}Total matches: $(cat "$AUDIT_FILE" | jq -r --arg league "$league" 'select(.match_data != null and .match_data.league == $league)' | wc -l | tr -d ' ')${NC}"
}

# Show statistics
show_stats() {
    check_file
    echo -e "${BLUE}=== Audit Statistics - $DATE ===${NC}\n"

    local total_events=$(cat "$AUDIT_FILE" | wc -l | tr -d ' ')
    local runs=$(cat "$AUDIT_FILE" | jq -r 'select(.event_type == "run_started")' | wc -l | tr -d ' ')
    local discovered=$(cat "$AUDIT_FILE" | jq -r 'select(.event_type == "match_discovered")' | wc -l | tr -d ' ')
    local updated=$(cat "$AUDIT_FILE" | jq -r 'select(.event_type == "match_updated")' | wc -l | tr -d ' ')
    local unchanged=$(cat "$AUDIT_FILE" | jq -r 'select(.event_type == "match_unchanged")' | wc -l | tr -d ' ')
    local queued=$(cat "$AUDIT_FILE" | jq -r 'select(.event_type == "queue_submitted")' | wc -l | tr -d ' ')
    local failed=$(cat "$AUDIT_FILE" | jq -r 'select(.event_type == "queue_failed")' | wc -l | tr -d ' ')

    echo -e "${GREEN}Total Audit Events:${NC}     $total_events"
    echo -e "${GREEN}Scraping Runs:${NC}          $runs"
    echo -e "${GREEN}Matches Discovered:${NC}     $discovered"
    echo -e "${GREEN}Matches Updated:${NC}        $updated"
    echo -e "${GREEN}Matches Unchanged:${NC}      $unchanged"
    echo -e "${GREEN}Queue Submitted:${NC}        $queued"
    echo -e "${GREEN}Queue Failed:${NC}           $failed"

    echo -e "\n${BLUE}By League:${NC}"
    cat "$AUDIT_FILE" | \
    jq -r 'select(.match_data != null) | .match_data.league // "Unknown"' | \
    sort | uniq -c | \
    awk '{printf "  %-20s %s matches\n", $2, $1}'
}

# Show only matches with changes
show_changes() {
    check_file
    echo -e "${BLUE}=== Match Updates (Changes) - $DATE ===${NC}\n"

    cat "$AUDIT_FILE" | \
    jq -r 'select(.event_type == "match_updated") |
           "\n#\(.match_data.external_match_id) | \(.match_data.home_team) vs \(.match_data.away_team)\n  Date: \(.match_data.match_date)\n  Changes: \(.changes | to_entries | map("\(.key): \(.value.from) → \(.value.to)") | join(", "))"'

    local count=$(cat "$AUDIT_FILE" | jq -r 'select(.event_type == "match_updated")' | wc -l | tr -d ' ')
    echo -e "\n${GREEN}Total updated matches: $count${NC}"
}

# Show queue errors
show_errors() {
    check_file
    echo -e "${RED}=== Queue Submission Errors - $DATE ===${NC}\n"

    cat "$AUDIT_FILE" | \
    jq -r 'select(.event_type == "queue_failed") |
           "#\(.correlation_id) | Error: \(.error_message)"'

    local count=$(cat "$AUDIT_FILE" | jq -r 'select(.event_type == "queue_failed")' | wc -l | tr -d ' ')
    echo -e "\n${RED}Total errors: $count${NC}"
}

# Show all scraping runs
show_runs() {
    check_file
    echo -e "${BLUE}=== Scraping Runs - $DATE ===${NC}\n"

    cat "$AUDIT_FILE" | \
    jq -r 'select(.event_type == "run_started" or .event_type == "run_completed") |
           if .event_type == "run_started" then
               "▶ Run Started: \(.run_id)\n  League: \(.run_metadata.league // "Unknown") | Age: \(.run_metadata.age_group // "?") | Division: \(.run_metadata.division // "?")\n  Date Range: \(.run_metadata.date_range // "?")"
           else
               "✓ Run Completed: \(.run_id)\n  Summary: \(.summary.total_matches // 0) total | \(.summary.discovered // 0) discovered | \(.summary.updated // 0) updated | \(.summary.queue_submitted // 0) queued\n"
           end'
}

# Show raw JSON
show_raw() {
    check_file
    cat "$AUDIT_FILE" | jq '.'
}

# Format audit event for tail display
format_event() {
    jq -r --arg CYAN $'\033[0;36m' \
          --arg GREEN $'\033[0;32m' \
          --arg BLUE $'\033[0;34m' \
          --arg YELLOW $'\033[1;33m' \
          --arg RED $'\033[0;31m' \
          --arg MAGENTA $'\033[0;35m' \
          --arg NC $'\033[0m' '
        # Format timestamp - Convert UTC to EDT and format as MM-DD-YYYY:HH:MM:SS
        (.timestamp // "" |
         if . != "" then
             # Strip microseconds and add Z for ISO8601 parsing
             ((. | split(".")[0]) + "Z" | fromdateiso8601 - 14400) | strftime("%m-%d-%Y:%H:%M:%S")
         else
             "??-??-????:??:??:??"
         end) as $time |

        # Format based on event type
        if .event_type == "run_started" then
            "\($CYAN)\($time)\($NC) | \($BLUE)▶ RUN STARTED\($NC) | \(.run_id) | League: \(.run_metadata.league // "?") | Age: \(.run_metadata.age_group // "?") | Div: \(.run_metadata.division // "?")"
        elif .event_type == "run_completed" then
            "\($CYAN)\($time)\($NC) | \($GREEN)✓ RUN COMPLETE\($NC) | \(.run_id) | Total: \(.summary.total_matches // 0) | New: \(.summary.discovered // 0) | Updated: \(.summary.updated // 0) | Queued: \(.summary.queue_submitted // 0)"
        elif .event_type == "match_discovered" then
            (if .match_data.home_score != null then "\(.match_data.home_team) (\(.match_data.home_score))" else .match_data.home_team end) as $home |
            (if .match_data.away_score != null then "\(.match_data.away_team) (\(.match_data.away_score))" else .match_data.away_team end) as $away |
            "\($CYAN)\($time)\($NC) | \($GREEN)✚ DISCOVERED\($NC) | #\(.match_data.external_match_id) | \($home) vs \($away) | \(.match_data.match_date) | \(.match_data.match_status)"
        elif .event_type == "match_updated" then
            (if .match_data.home_score != null then "\(.match_data.home_team) (\(.match_data.home_score))" else .match_data.home_team end) as $home |
            (if .match_data.away_score != null then "\(.match_data.away_team) (\(.match_data.away_score))" else .match_data.away_team end) as $away |
            "\($CYAN)\($time)\($NC) | \($YELLOW)⟳ UPDATED\($NC) | #\(.match_data.external_match_id) | \($home) vs \($away) | \(.match_data.match_date) | Changes: \(.changes | to_entries | map("\(.key)") | join(", "))"
        elif .event_type == "match_unchanged" then
            (if .match_data.home_score != null then "\(.match_data.home_team) (\(.match_data.home_score))" else .match_data.home_team end) as $home |
            (if .match_data.away_score != null then "\(.match_data.away_team) (\(.match_data.away_score))" else .match_data.away_team end) as $away |
            "\($CYAN)\($time)\($NC) | \($BLUE)≡ UNCHANGED\($NC) | #\(.match_data.external_match_id) | \($home) vs \($away) | \(.match_data.match_date)"
        elif .event_type == "queue_submitted" then
            "\($CYAN)\($time)\($NC) | \($GREEN)→ QUEUED\($NC) | #\(.correlation_id) | Match: \(.match_id // "?")"
        elif .event_type == "queue_failed" then
            "\($CYAN)\($time)\($NC) | \($RED)✗ QUEUE ERROR\($NC) | #\(.correlation_id) | \(.error_message)"
        else
            "\($CYAN)\($time)\($NC) | \($MAGENTA)\(.event_type)\($NC) | \(.run_id // .correlation_id // "?")"
        end
    '
}

# Get jq filter based on event type
get_type_filter() {
    local type="$1"
    case "$type" in
        match)
            echo 'select(.event_type == "match_discovered" or .event_type == "match_updated")'
            ;;
        error)
            echo 'select(.event_type == "queue_failed")'
            ;;
        run)
            echo 'select(.event_type == "run_started" or .event_type == "run_completed")'
            ;;
        queue)
            echo 'select(.event_type == "queue_submitted" or .event_type == "queue_failed")'
            ;;
        all|*)
            echo 'select(true)'
            ;;
    esac
}

# Tail mode - show recent events
show_tail() {
    local follow=false
    local lines=20
    local event_type="all"

    # Parse tail-specific options
    shift  # Remove 'tail' command
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -f|--follow)
                follow=true
                shift
                ;;
            -n)
                lines="$2"
                shift 2
                ;;
            -t|--type)
                event_type="$2"
                shift 2
                ;;
            *)
                echo -e "${RED}Error: Unknown tail option: $1${NC}"
                echo "Usage: $0 tail [-f] [-n lines] [-t type]"
                exit 1
                ;;
        esac
    done

    check_file

    local type_filter=$(get_type_filter "$event_type")
    local type_label=$(echo "$event_type" | tr '[:lower:]' '[:upper:]')

    if [ "$follow" = true ]; then
        echo -e "${BLUE}=== Following Audit Log - $DATE ($type_label) ===${NC}"
        echo -e "${YELLOW}Press Ctrl+C to stop${NC}\n"

        # Show initial recent events
        tail -n "$lines" "$AUDIT_FILE" | jq -c "$type_filter" 2>/dev/null | format_event

        # Follow new events
        tail -f -n 0 "$AUDIT_FILE" | while read -r line; do
            echo "$line" | jq -c "$type_filter" 2>/dev/null | format_event
        done
    else
        echo -e "${BLUE}=== Recent Audit Events - $DATE ($type_label) ===${NC}\n"
        tail -n "$lines" "$AUDIT_FILE" | jq -c "$type_filter" 2>/dev/null | format_event
        echo ""
    fi
}

# Trap Ctrl+C for clean exit in follow mode
trap 'echo -e "\n${YELLOW}Stopped following audit log${NC}"; exit 0' INT

# Main command dispatcher
case "${1:-help}" in
    all)
        show_all
        ;;
    team)
        show_team "$2"
        ;;
    league)
        show_league "$2"
        ;;
    stats)
        show_stats
        ;;
    changes)
        show_changes
        ;;
    errors)
        show_errors
        ;;
    runs)
        show_runs
        ;;
    tail)
        show_tail "$@"
        ;;
    raw)
        show_raw
        ;;
    help|--help|-h)
        usage
        ;;
    *)
        echo -e "${RED}Error: Unknown command: $1${NC}\n"
        usage
        ;;
esac
