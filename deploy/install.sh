#!/usr/bin/env bash
# deploy/install.sh — El Patriota gateway installer for a bare-metal VPS.
#
# Tested on Ubuntu 22.04+ / Debian 12+. Run as root.
#
# What it does:
#   1. Creates a system user `patriota` to run the service.
#   2. Installs the Hermes CLI for that user.
#   3. Creates a Python venv at /opt/patriota/venv and installs patriota-tools.
#   4. Copies config, persona, skills, and prompts to the Hermes home directory.
#   5. Writes a secrets template to /etc/patriota/env (fill in before starting).
#   6. Installs and enables the systemd service.
#
# Usage:
#   sudo bash deploy/install.sh
#
# After install, fill in /etc/patriota/env, then:
#   sudo systemctl start patriota-gateway
#   sudo journalctl -u patriota-gateway -f
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_USER="patriota"
HERMES_HOME="/home/$INSTALL_USER/.hermes"
VENV_DIR="/opt/patriota/venv"
STATIC_DIR="/opt/patriota"
ENV_FILE="/etc/patriota/env"
SERVICE_NAME="patriota-gateway"
SERVICE_FILE="/etc/systemd/system/$SERVICE_NAME.service"

# ── helpers ──────────────────────────────────────────────────────────────────
info()  { echo "==> $*"; }
check() { echo "  ✓ $*"; }
warn()  { echo "  ! $*"; }

require_root() {
    if [ "$EUID" -ne 0 ]; then
        echo "Error: run this script as root (sudo bash deploy/install.sh)"
        exit 1
    fi
}

# ── 1. System user ────────────────────────────────────────────────────────────
create_user() {
    info "Creating system user '$INSTALL_USER'..."
    if id "$INSTALL_USER" &>/dev/null; then
        check "user already exists"
    else
        useradd --system --create-home --shell /bin/bash "$INSTALL_USER"
        check "user created"
    fi
}

# ── 2. Hermes CLI ─────────────────────────────────────────────────────────────
install_hermes() {
    info "Installing Hermes CLI..."
    if su -l "$INSTALL_USER" -c "command -v hermes" &>/dev/null; then
        check "hermes already installed ($(su -l "$INSTALL_USER" -c "hermes --version" 2>/dev/null || echo 'version unknown'))"
    else
        su -l "$INSTALL_USER" -c \
            "curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash"
        check "hermes installed"
    fi

    HERMES_BIN="$(su -l "$INSTALL_USER" -c "command -v hermes")"
    check "hermes binary: $HERMES_BIN"
}

# ── 3. Python venv + patriota-tools ──────────────────────────────────────────
install_tools() {
    info "Installing patriota-tools into $VENV_DIR..."
    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install --quiet --upgrade pip
    "$VENV_DIR/bin/pip" install --quiet "$REPO_DIR"
    chown -R root:root "$VENV_DIR"   # root-owned, world-readable
    check "patriota-tools installed ($("$VENV_DIR/bin/patriota-tools" --version 2>/dev/null || echo 'ok'))"
}

# ── 4. Static assets (prompts, sources, skills, persona) ─────────────────────
copy_assets() {
    info "Copying static assets to $STATIC_DIR and $HERMES_HOME..."

    # Startup script, prompts, and sources: owned by root, read by all
    install -d -m 755 "$STATIC_DIR/prompts" "$STATIC_DIR/config"
    install -m 755 "$REPO_DIR/hermes/scripts/start-gateway.sh" "$STATIC_DIR/start-gateway.sh"
    cp "$REPO_DIR/hermes/prompts/"*.md  "$STATIC_DIR/prompts/"
    cp "$REPO_DIR/config/sources.yaml"  "$STATIC_DIR/config/"
    check "start-gateway.sh, prompts, and sources copied to $STATIC_DIR"

    # Hermes home: owned by patriota (Hermes writes memory/sessions/cron here)
    su -l "$INSTALL_USER" -c "mkdir -p $HERMES_HOME/skills"
    install -o "$INSTALL_USER" -m 644 \
        "$REPO_DIR/hermes/AGENTS.md"   "$HERMES_HOME/AGENTS.md"
    install -o "$INSTALL_USER" -m 644 \
        "$REPO_DIR/hermes/config.yaml" "$HERMES_HOME/config.yaml"
    cp -r "$REPO_DIR/hermes/skills/." "$HERMES_HOME/skills/"
    chown -R "$INSTALL_USER" "$HERMES_HOME/skills"
    check "AGENTS.md, config.yaml, and skills copied to $HERMES_HOME"
}

# ── 5. Env file template ──────────────────────────────────────────────────────
write_env_template() {
    info "Writing env template to $ENV_FILE..."
    mkdir -p /etc/patriota

    if [ -f "$ENV_FILE" ]; then
        warn "$ENV_FILE already exists — not overwriting"
        return
    fi

    # Resolve hermes binary path for PATH in service
    HERMES_BIN_DIR="$(dirname "$(su -l "$INSTALL_USER" -c "command -v hermes")")"

    cat > "$ENV_FILE" << EOF
# /etc/patriota/env — El Patriota gateway secrets.
# Fill in all required values, then: sudo systemctl start patriota-gateway

# ── LLM provider (pick one) ──────────────────────────────────────────────────
OPENROUTER_API_KEY=          # required for OpenAI models via OpenRouter
# ANTHROPIC_API_KEY=         # optional — if switching to an Anthropic model
# HERMES_MODEL=              # override model (default: openai/gpt-4o-mini)
                              # to change at runtime edit this and restart

# ── Telegram gateway ──────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN=          # from @BotFather
TELEGRAM_HOME_CHANNEL=       # chat_id of the editorial group (negative int)
TELEGRAM_ALLOWED_USERS=      # your Telegram user id (e.g. 123456789)

# ── External integrations ─────────────────────────────────────────────────────
TWITTERAPI_IO_KEY=           # twitterapi.io key for X/Twitter monitoring
CMS_BASE_URL=                # CMS REST endpoint
CMS_API_TOKEN=               # CMS API token

# ── Resolved by install.sh — do not edit unless you move things ──────────────
HERMES_HOME=$HERMES_HOME
HERMES_WORKDIR=$HERMES_HOME
PATH=$HERMES_BIN_DIR:/usr/local/bin:/usr/bin:/bin
PATRIOTA_INSTALL_MCP=$VENV_DIR/bin/patriota-install-mcp
PATRIOTA_MCP_COMMAND=$VENV_DIR/bin/patriota-tools
PATRIOTA_DB_PATH=$HERMES_HOME/patriota.db
PATRIOTA_PROMPTS_DIR=$STATIC_DIR/prompts
USE_MOCKS=false
EOF
    chmod 640 "$ENV_FILE"
    chown root:"$INSTALL_USER" "$ENV_FILE"
    check "$ENV_FILE written — fill in secrets before starting the service"
}

# ── 6. systemd service ────────────────────────────────────────────────────────
install_service() {
    info "Installing systemd service $SERVICE_NAME..."
    cp "$REPO_DIR/deploy/patriota-gateway.service" "$SERVICE_FILE"
    systemctl daemon-reload
    systemctl enable "$SERVICE_NAME"
    check "service installed and enabled (not started yet)"
}

# ── main ──────────────────────────────────────────────────────────────────────
require_root
create_user
install_hermes
install_tools
copy_assets
write_env_template
install_service

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " Install complete. Next steps:"
echo ""
echo "  1. Fill in secrets:  nano $ENV_FILE"
echo "  2. Start service:    sudo systemctl start $SERVICE_NAME"
echo "  3. Follow logs:      sudo journalctl -u $SERVICE_NAME -f"
echo ""
echo " To update after a code change:"
echo "   git pull && sudo bash deploy/install.sh && sudo systemctl restart $SERVICE_NAME"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
