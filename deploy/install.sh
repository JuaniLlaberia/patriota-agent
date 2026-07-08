#!/usr/bin/env bash
# deploy/install.sh — El Patriota gateway installer for a bare-metal VPS.
#
# Tested on Ubuntu 22.04+ / Debian 12+. Run as root.
#
# What it does:
#   1. Creates a system user `patriota` to run the service.
#   2. Installs the Hermes CLI for that user.
#   3. Creates a Python venv at /opt/patriota/venv and installs patriota-tools.
#   4. Copies config, persona, skills, and prompts to both the Hermes home and
#      a root-owned canonical location (/opt/patriota/skills/) that start-gateway.sh
#      uses to reset skills on every start (prevents self-improvement drift).
#   5. Initializes the DB and its tables if they do not exist (idempotent).
#   6. Removes the cron sentinel so updated job definitions are re-seeded on next start.
#   7. Writes a secrets template to /etc/patriota/env (fill in before starting).
#   8. Installs and enables the systemd service.
#   9. Installs a health-check cron that alerts Telegram on service/credit failures.
#
# This script never wipes DB data or agent memory — run wipe-agent.sh first for that.
#
# Usage:
#   sudo bash deploy/install.sh
#
# After install, fill in /etc/patriota/env, then:
#   sudo systemctl start patriota-gateway
#   sudo journalctl -u patriota-gateway -f
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# ── 0. System prerequisites ───────────────────────────────────────────────────
install_prerequisites() {
    info "Installing system prerequisites..."
    apt-get install -y -q python3-venv ripgrep ffmpeg sqlite3
    check "python3-venv, ripgrep, ffmpeg, sqlite3 installed"
}
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
    info "Installing/updating patriota-tools into $VENV_DIR..."
    if [ ! -d "$VENV_DIR" ]; then
        python3 -m venv "$VENV_DIR"
        "$VENV_DIR/bin/pip" install --quiet --upgrade pip
    fi
    # Always force-reinstall so code changes in the repo are picked up on every deploy.
    "$VENV_DIR/bin/pip" install --quiet --force-reinstall "$REPO_DIR"
    chown -R root:root "$VENV_DIR"   # root-owned, world-readable
    check "patriota-tools installed/updated"
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

    # Canonical skills: root-owned, world-readable, NOT writable by patriota.
    # start-gateway.sh copies from here to ~/.hermes/skills/ on every start,
    # reverting any self-improvement patches and removing agent-created skills.
    install -d -m 755 "$STATIC_DIR/skills"
    cp -r "$REPO_DIR/hermes/skills/." "$STATIC_DIR/skills/"
    find "$STATIC_DIR/skills" -type f -exec chmod 644 {} \;
    find "$STATIC_DIR/skills" -type d -exec chmod 755 {} \;
    check "canonical skills saved to $STATIC_DIR/skills (root-owned)"

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

# ── 4b. Initialize DB ────────────────────────────────────────────────────────
init_db() {
    info "Initializing editorial DB (skipped if already up to date)..."
    DB_PATH="$HERMES_HOME/patriota.db"
    # init_db uses CREATE TABLE IF NOT EXISTS and runs migrations idempotently,
    # so this is safe to call on every deploy — it only creates what is missing.
    PATRIOTA_DB_PATH="$DB_PATH" "$VENV_DIR/bin/python" -c \
        "from patriota_tools.storage import db; db.init_db('$DB_PATH')"
    chown "$INSTALL_USER" "$DB_PATH"
    check "DB ready at $DB_PATH"
}

# ── 4c. Reset cron sentinel ───────────────────────────────────────────────────
reset_state() {
    info "Resetting cron sentinel for fresh deploy..."

    # Remove sentinel so start-gateway.sh re-creates cron jobs with updated
    # definitions from code on next start. DB and agent memory are never touched
    # here — use wipe-agent.sh for a full factory reset.
    rm -f "$HERMES_HOME/.cron-seeded"
    check "cron sentinel removed (jobs re-seed on next start)"
}

# ── 5. Env file template ──────────────────────────────────────────────────────
write_env_template() {
    info "Writing env file to $ENV_FILE..."
    mkdir -p /etc/patriota

    # Resolve hermes binary path for PATH in service
    HERMES_BIN_DIR="$(dirname "$(su -l "$INSTALL_USER" -c "command -v hermes")")"

    if [ ! -f "$ENV_FILE" ]; then
        # Fresh install — write the full template including secrets placeholders
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

# ── AI / LLM ─────────────────────────────────────────────────────────────────
OPENAI_API_KEY=              # For embeddings (text-embedding-3-small, OpenAI direct)
OPENROUTER_API_KEY=          # For article generation via GPT-4o-mini (OpenRouter)

# ── CMS OAuth v1.1 ───────────────────────────────────────────────────────────
CMS_API_URL_BASE=            # CMS REST base URL (e.g. https://api.elpatriota.com)
CMS_CLIENT_ID=               # OAuth client ID
CMS_CLIENT_SECRET=           # OAuth client secret
CMS_USERNAME=                # CMS user with API permissions
CMS_PASSWORD=                # CMS user password

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
    else
        # Re-deploy — secrets are preserved; only update/add the resolved vars
        # (paths computed by install.sh that may change between deploys).
        warn "$ENV_FILE already exists — preserving secrets, updating resolved vars"
        _upsert_env() {
            local key="$1" val="$2"
            if grep -q "^${key}=" "$ENV_FILE"; then
                sed -i "s|^${key}=.*|${key}=${val}|" "$ENV_FILE"
            else
                echo "${key}=${val}" >> "$ENV_FILE"
            fi
        }
        _upsert_env "HERMES_HOME"           "$HERMES_HOME"
        _upsert_env "HERMES_WORKDIR"        "$HERMES_HOME"
        _upsert_env "PATH"                  "$HERMES_BIN_DIR:/usr/local/bin:/usr/bin:/bin"
        _upsert_env "PATRIOTA_INSTALL_MCP"  "$VENV_DIR/bin/patriota-install-mcp"
        _upsert_env "PATRIOTA_MCP_COMMAND"  "$VENV_DIR/bin/patriota-tools"
        _upsert_env "PATRIOTA_DB_PATH"      "$HERMES_HOME/patriota.db"
        _upsert_env "PATRIOTA_PROMPTS_DIR"  "$STATIC_DIR/prompts"
        _upsert_env "USE_MOCKS"             "false"
        check "resolved vars updated in $ENV_FILE"
    fi
}

# ── 6. systemd service ────────────────────────────────────────────────────────
install_service() {
    info "Installing systemd service $SERVICE_NAME..."
    cp "$REPO_DIR/deploy/patriota-gateway.service" "$SERVICE_FILE"
    systemctl daemon-reload
    systemctl enable "$SERVICE_NAME"
    check "service installed and enabled (not started yet)"
}

# ── 7. Health check cron ──────────────────────────────────────────────────────
install_health_check() {
    info "Installing health check..."
    install -m 755 "$REPO_DIR/deploy/health-check.sh" "$STATIC_DIR/health-check.sh"
    cat > "/etc/cron.d/patriota-health" << 'CRONEOF'
# El Patriota — service health check (every 15 min)
*/15 * * * * root /opt/patriota/health-check.sh >> /var/log/patriota-health.log 2>&1
CRONEOF
    chmod 644 "/etc/cron.d/patriota-health"
    check "health check installed at /etc/cron.d/patriota-health (every 15 min)"
}

# ── main ──────────────────────────────────────────────────────────────────────
require_root
install_prerequisites
create_user
install_hermes
install_tools
copy_assets
init_db
reset_state
write_env_template
install_service
install_health_check

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
