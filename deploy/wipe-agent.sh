#!/usr/bin/env bash
# deploy/wipe-agent.sh — Full factory reset of the Hermes agent.
#
# Wipes every location where Hermes stores state so the agent starts
# completely fresh with no memory of previous sessions:
#
#   • ~/.hermes/memory/          — conversation memory summaries
#   • ~/.hermes/sessions/        — full session transcripts
#   • ~/.hermes/conversations/   — alternate session store (Hermes version-dependent)
#   • ~/.hermes/user_profile*    — learned user/tool behaviors (user_profile_enabled)
#   • ~/.hermes/profile/         — alternate profile store
#   • ~/.hermes/cache/           — cached responses
#   • ~/.hermes/tmp/             — temp files
#   • ~/.hermes/.cron-seeded     — cron sentinel (forces re-seed on next start)
#   • ~/.hermes/*.json           — any top-level state JSON files
#   • patriota.db editorial tables — articles, clusters, tweets, prompts, logs
#
# What is NOT wiped (needed for the agent to function):
#   • ~/.hermes/AGENTS.md        — persona (restored by install.sh)
#   • ~/.hermes/config.yaml      — configuration
#   • ~/.hermes/skills/          — skill files (synced from canonical on every start)
#
# Usage: sudo bash deploy/wipe-agent.sh
set -euo pipefail

SERVICE="patriota-gateway"
INSTALL_USER="patriota"
HERMES_HOME="/home/$INSTALL_USER/.hermes"
DB_PATH="$HERMES_HOME/patriota.db"

info()  { echo "==> $*"; }
check() { echo "  ✓ $*"; }

require_root() {
    if [ "$EUID" -ne 0 ]; then
        echo "Error: run as root (sudo bash deploy/wipe-agent.sh)"
        exit 1
    fi
}

require_root

# ── 1. Stop the service ───────────────────────────────────────────────────────
info "Stopping $SERVICE..."
systemctl stop "$SERVICE" || true
check "service stopped"

# ── 2. Wipe all Hermes agent state ───────────────────────────────────────────
info "Wiping Hermes agent memory and state..."

wipe() {
    if [ -e "$1" ]; then
        rm -rf "$1"
        echo "  wiped: $1"
    fi
}

# Conversation memory
wipe "$HERMES_HOME/memory"

# Session / conversation history (Hermes stores these in one of these locations)
wipe "$HERMES_HOME/sessions"
wipe "$HERMES_HOME/conversations"

# User profile — learned tool names, preferences, behaviors
# (user_profile_enabled: true in config.yaml; most likely cause of stale tool names)
wipe "$HERMES_HOME/user_profile.json"
wipe "$HERMES_HOME/user_profile"
wipe "$HERMES_HOME/profile"

# Cache and temp
wipe "$HERMES_HOME/cache"
wipe "$HERMES_HOME/tmp"

# Top-level state JSON files (catch-all for any Hermes version quirks)
find "$HERMES_HOME" -maxdepth 1 -name "*.json" -delete 2>/dev/null && echo "  wiped: $HERMES_HOME/*.json" || true

# Cron sentinel — forces start-gateway.sh to re-seed cron jobs on next start
wipe "$HERMES_HOME/.cron-seeded"
wipe "$HERMES_HOME/.needs-clean"

check "all Hermes state wiped"

# ── 3. Wipe editorial DB ──────────────────────────────────────────────────────
info "Wiping editorial DB..."

if [ -f "$DB_PATH" ]; then
    rm -f "$DB_PATH"
    check "DB deleted ($DB_PATH)"
else
    echo "  ! $DB_PATH not found — nothing to delete"
fi

# ── 4. Restart ────────────────────────────────────────────────────────────────
info "Starting $SERVICE..."
systemctl start "$SERVICE"
check "service started — agent starts completely fresh"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " Factory reset complete."
echo " Follow logs: sudo journalctl -u $SERVICE -f"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
