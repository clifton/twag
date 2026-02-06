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
#   TELEGRAM_CHAT_ID - For error notifications (optional)
#   TELEGRAM_BOT_TOKEN - For error notifications (optional)
#   OPENCLAW_TOKEN - For error notifications via OpenClaw gateway (optional)

# Load environment from common locations
for envfile in ~/.env ~/.config/twag/env /etc/twag/env; do
    # shellcheck disable=SC1090
    [ -f "$envfile" ] && source "$envfile" 2>/dev/null || true
done

# Ensure PATH includes common install locations
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

# Validate twag is available
if ! command -v twag >/dev/null 2>&1; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') [twag] ERROR: twag not found in PATH" >&2
    exit 1
fi

# Prevent concurrent runs (flock may not be available on macOS)
if command -v flock >/dev/null 2>&1; then
    LOCK_FILE="${TWAG_DATA_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/twag}/cron.lock"
    exec 9>"$LOCK_FILE"
    if ! flock -n 9; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') [twag] Another instance is running, skipping"
        exit 0
    fi
fi

MODE="${1:-full}"
ERRORS=""

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [twag] $*"
}

notify_error() {
    local msg="$1"
    log "ERROR: $msg"

    # Try OpenClaw gateway first (if running locally)
    if [ -n "$OPENCLAW_TOKEN" ] && curl -sf --max-time 3 --connect-timeout 2 http://127.0.0.1:8443/health >/dev/null 2>&1; then
        local json_msg="${msg//$'\n'/\\n}"
        curl -sf --max-time 10 --connect-timeout 5 -X POST "http://127.0.0.1:8443/api/message" \
            -H "Authorization: Bearer $OPENCLAW_TOKEN" \
            -H "Content-Type: application/json" \
            -d "{\"channel\":\"telegram\",\"to\":\"${TELEGRAM_CHAT_ID}\",\"message\":\"⚠️ twag pipeline failed:\\n${json_msg}\"}" \
            >/dev/null 2>&1 && return 0
    fi

    # Fallback to direct Telegram API
    if [ -n "$TELEGRAM_BOT_TOKEN" ] && [ -n "$TELEGRAM_CHAT_ID" ]; then
        curl -sf --max-time 10 --connect-timeout 5 -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
            -d "chat_id=${TELEGRAM_CHAT_ID}" \
            -d "text=⚠️ twag pipeline failed: ${msg}" \
            >/dev/null 2>&1 && return 0
    fi

    # No notification method available
    log "WARNING: Could not send error notification (no TELEGRAM_BOT_TOKEN or OPENCLAW_TOKEN)"
}

run_cmd() {
    local desc="$1"
    shift

    if ! "$@"; then
        ERRORS="${ERRORS}${desc} failed"$'\n'
        return 1
    fi
    return 0
}

case "$MODE" in
    full)
        # Full cycle: fetch, process, digest, maintenance
        log "Running full cycle..."
        run_cmd "fetch" twag fetch || true
        run_cmd "process" twag process || true
        run_cmd "digest" twag digest || true
        run_cmd "decay" twag accounts decay || true
        run_cmd "prune" twag prune --days 14 || true
        ;;
    fetch-only)
        # Quick fetch during the day (no tier-1 to reduce API calls)
        log "Running fetch only..."
        run_cmd "fetch" twag fetch --no-tier1 || true
        ;;
    process-only)
        log "Running process only..."
        run_cmd "process" twag process || true
        ;;
    digest-only)
        log "Running digest only..."
        run_cmd "digest" twag digest || true
        ;;
    *)
        echo "Usage: $0 [full|fetch-only|process-only|digest-only]"
        exit 1
        ;;
esac

if [ -n "$ERRORS" ]; then
    notify_error "$ERRORS"
    log "Completed with errors"
    exit 1
fi

log "Done"
