#!/bin/bash
# deploy/health-check.sh — El Patriota service health monitor.
#
# Installed to /opt/patriota/health-check.sh by install.sh.
# Runs every 15 min via /etc/cron.d/patriota-health (as root).
# Sends a Telegram alert on the FIRST failure in a window; silences until resolved.
#
# Checks:
#   1. patriota-gateway systemd service is active
#   2. More than 2 cron job failures in the last 2 hours
#   3. OpenRouter 402 (credits exhausted) in the last hour
#   4. Editorial prompts (editorial, filtering, twitter) exist in the DB

set -uo pipefail

ENV_FILE="/etc/patriota/env"
DB_PATH="/home/patriota/.hermes/patriota.db"
ALERT_STAMP="/tmp/patriota-health-alerted"
ALERT_COOLDOWN=3600   # seconds between repeated Telegram alerts for the same outage

# ── Load credentials ──────────────────────────────────────────────────────────
[ -f "$ENV_FILE" ] || { logger -t patriota-health "ERROR: $ENV_FILE missing"; exit 1; }

get_env() {
    # Extract VALUE from KEY=VALUE lines, stripping inline comments and whitespace.
    grep -m1 "^${1}=" "$ENV_FILE" 2>/dev/null \
        | cut -d= -f2- | sed 's/[[:space:]]*#.*//' | tr -d '[:space:]'
}

BOT_TOKEN=$(get_env TELEGRAM_BOT_TOKEN)
CHANNEL=$(get_env TELEGRAM_HOME_CHANNEL)

# ── Alert helper ──────────────────────────────────────────────────────────────
send_alert() {
    local msg="$1"
    # Rate-limit: only send if last alert was more than ALERT_COOLDOWN seconds ago
    if [ -f "$ALERT_STAMP" ]; then
        local last_alert
        last_alert=$(cat "$ALERT_STAMP" 2>/dev/null || echo 0)
        local now
        now=$(date +%s)
        if [ $(( now - last_alert )) -lt "$ALERT_COOLDOWN" ]; then
            return
        fi
    fi

    if [ -n "${BOT_TOKEN:-}" ] && [ -n "${CHANNEL:-}" ]; then
        curl -sS --max-time 10 -X POST \
            "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
            --data-urlencode "chat_id=${CHANNEL}" \
            --data-urlencode "text=${msg}" \
            -d "parse_mode=HTML" \
            > /dev/null 2>&1 || true
    fi

    date +%s > "$ALERT_STAMP"
    logger -t patriota-health "ALERT SENT: ${msg}"
}

resolve_alert() {
    # Clear the cooldown stamp when all checks pass
    rm -f "$ALERT_STAMP"
}

# ── Checks ────────────────────────────────────────────────────────────────────
ISSUES=()

# 1. Service alive?
if ! systemctl is-active --quiet patriota-gateway 2>/dev/null; then
    ISSUES+=("⛔ <b>patriota-gateway no está corriendo</b>")
fi

# 2. Too many cron failures recently?
if command -v journalctl > /dev/null 2>&1; then
    CRON_ERRORS=$(journalctl -u patriota-gateway --since "2 hours ago" --no-pager -q 2>/dev/null \
        | grep -c "ERROR cron.scheduler" || true)
    if [ "${CRON_ERRORS:-0}" -gt 2 ]; then
        ISSUES+=("⚠️ <b>${CRON_ERRORS} fallas de cron en las últimas 2 horas</b>")
    fi

    # 3. OpenRouter credits exhausted?
    API_402=$(journalctl -u patriota-gateway --since "1 hour ago" --no-pager -q 2>/dev/null \
        | grep -c "HTTP 402" || true)
    if [ "${API_402:-0}" -gt 0 ]; then
        ISSUES+=("💸 <b>Sin créditos OpenRouter</b> — recargá en openrouter.ai/settings/credits")
    fi
fi

# 4. Prompts seeded in DB?
if command -v sqlite3 > /dev/null 2>&1 && [ -f "$DB_PATH" ]; then
    for prompt in editorial filtering twitter; do
        count=$(sqlite3 "$DB_PATH" \
            "SELECT COUNT(*) FROM prompt_versions WHERE name='${prompt}';" 2>/dev/null || echo "0")
        if [ "${count:-0}" = "0" ]; then
            ISSUES+=("⚠️ Prompt '<code>${prompt}</code>' no encontrado en la DB")
        fi
    done
fi

# ── Report ────────────────────────────────────────────────────────────────────
if [ "${#ISSUES[@]}" -gt 0 ]; then
    BODY=""
    for issue in "${ISSUES[@]}"; do
        BODY="${BODY}• ${issue}
"
    done
    MSG="🚨 <b>El Patriota — Alerta de salud</b>

${BODY}
$(date -u '+%d/%m/%Y %H:%M UTC')"
    send_alert "$MSG"
    exit 1
else
    resolve_alert
    logger -t patriota-health "OK"
fi
