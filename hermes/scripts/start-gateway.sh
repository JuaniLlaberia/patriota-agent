#!/bin/sh
# start-gateway.sh — runs on every gateway start.
# 1. Registers/updates the MCP server config (picks up current env vars).
# 2. Seeds the 3 recurring cron jobs on first run only (idempotent).
# 3. Launches the Hermes gateway.
#
# Key env vars (set in /etc/patriota/env or exported before running):
#   PATRIOTA_INSTALL_MCP  — path to patriota-install-mcp binary
#                           (default: patriota-install-mcp, must be in PATH)
#   HERMES_WORKDIR        — dir that Hermes uses as workdir for cron jobs;
#                           AGENTS.md must exist there (default: $HOME/.hermes)
#   PATRIOTA_SEED_DONE    — sentinel file path; delete it to force a re-seed
#                           (default: $HERMES_WORKDIR/.cron-seeded)
set -eu

HERMES_WORKDIR="${HERMES_WORKDIR:-$HOME/.hermes}"
PATRIOTA_INSTALL_MCP="${PATRIOTA_INSTALL_MCP:-patriota-install-mcp}"
PATRIOTA_SEED_DONE="${PATRIOTA_SEED_DONE:-$HERMES_WORKDIR/.cron-seeded}"

echo "==> Registrando MCP patriota-tools..."
"$PATRIOTA_INSTALL_MCP"

echo "==> Verificando cron jobs..."

if [ -f "$PATRIOTA_SEED_DONE" ]; then
    echo "  ya sembrados (eliminar $PATRIOTA_SEED_DONE para re-sembrar)"
else
    echo "  primera ejecución — sembrando cron jobs..."

    _seed_cron() {
        _name="$1"; shift
        hermes cron create "$@" --name "$_name"
        echo "  seeded: $_name"
    }

    _seed_cron monitoreo \
        "every 45m" \
        "Ejecutá un ciclo de monitoreo editorial. Usá la skill editorial-flow: corré mcp_patriota_ingest_all, agrupá fuentes relacionadas (mínimo 2) y proponé al grupo los títulos candidatos numerados. No publiques nada; esperá la aprobación del equipo." \
        --skill editorial-flow \
        --deliver telegram \
        --workdir "$HERMES_WORKDIR"

    _seed_cron twitter-diario \
        "0 12 * * *" \
        "Ejecutá el ciclo diario de Twitter con la skill twitter-flow: traé tendencias (WOEID 455827), filtrá según el prompt twitter y proponé al grupo borradores de tweets numerados. No publiques sin /aprobar." \
        --skill twitter-flow \
        --deliver telegram \
        --workdir "$HERMES_WORKDIR"

    _seed_cron resumen-semanal \
        "0 13 * * 1" \
        "Generá el resumen semanal con la skill weekly-summary y publicalo al CMS en estado borrador; avisá al grupo." \
        --skill weekly-summary \
        --deliver telegram \
        --workdir "$HERMES_WORKDIR"

    touch "$PATRIOTA_SEED_DONE"
    echo "  listo — re-sembrá borrando $PATRIOTA_SEED_DONE y reiniciando"
fi

echo "==> Iniciando hermes gateway..."
exec hermes gateway
