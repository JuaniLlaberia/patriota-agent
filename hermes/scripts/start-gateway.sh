#!/bin/sh
# start-gateway.sh — runs on every container start.
# 1. Registers/updates the MCP server config (picks up current env vars).
# 2. Seeds the 3 recurring cron jobs (remove + recreate = always in sync with this file).
# 3. Launches the Hermes gateway.
set -eu

echo "==> Registrando MCP patriota-tools..."
/opt/patriota/venv/bin/patriota-install-mcp

echo "==> Seeding cron jobs..."

_seed_cron() {
    _name="$1"; shift
    hermes cron remove "$_name" >/dev/null 2>&1 || true
    hermes cron create "$@" --name "$_name"
    echo "  seeded: $_name"
}

_seed_cron monitoreo \
    "every 45m" \
    "Ejecutá un ciclo de monitoreo editorial. Usá la skill editorial-flow: corré mcp_patriota_ingest_all, agrupá fuentes relacionadas (mínimo 2) y proponé al grupo los títulos candidatos numerados. No publiques nada; esperá la aprobación del equipo." \
    --skill editorial-flow \
    --deliver telegram \
    --workdir /opt/data

_seed_cron twitter-diario \
    "0 12 * * *" \
    "Ejecutá el ciclo diario de Twitter con la skill twitter-flow: traé tendencias (WOEID 455827), filtrá según el prompt twitter y proponé al grupo borradores de tweets numerados. No publiques sin /aprobar." \
    --skill twitter-flow \
    --deliver telegram \
    --workdir /opt/data

_seed_cron resumen-semanal \
    "0 13 * * 1" \
    "Generá el resumen semanal con la skill weekly-summary y publicalo al CMS en estado borrador; avisá al grupo." \
    --skill weekly-summary \
    --deliver telegram \
    --workdir /opt/data

echo "==> Iniciando hermes gateway..."
exec hermes gateway
