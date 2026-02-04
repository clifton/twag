#!/bin/bash
# Cron runner for twag
#
# Add to crontab:
#   0 7 * * * ~/.local/bin/twag-cron full
#   */30 7-22 * * * ~/.local/bin/twag-cron fetch-only
#
# Or if twag is in PATH:
#   0 7 * * * /path/to/cron-runner.sh full
#   */30 7-22 * * * /path/to/cron-runner.sh fetch-only
#
# Environment variables:
#   TWAG_DATA_DIR - Override data directory (optional)
#   AUTH_TOKEN, CT0 - Twitter auth (required)
#   GEMINI_API_KEY - For triage/vision (required)
#   ANTHROPIC_API_KEY - For enrichment (optional)

set -e

# Load environment from common locations
for envfile in ~/.env ~/.config/twag/env /etc/twag/env; do
    [ -f "$envfile" ] && source "$envfile" 2>/dev/null || true
done

# Ensure PATH includes common install locations
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

MODE="${1:-full}"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [twag] $*"
}

case "$MODE" in
    full)
        # Full cycle: fetch, process, digest, maintenance
        log "Running full cycle..."
        twag fetch
        twag process
        twag digest
        twag accounts decay
        twag prune --days 14
        ;;
    fetch-only)
        # Quick fetch during the day (no tier-1 to reduce API calls)
        log "Running fetch only..."
        twag fetch --no-tier1
        ;;
    process-only)
        log "Running process only..."
        twag process
        ;;
    digest-only)
        log "Running digest only..."
        twag digest
        ;;
    *)
        echo "Usage: $0 [full|fetch-only|process-only|digest-only]"
        exit 1
        ;;
esac

log "Done"
