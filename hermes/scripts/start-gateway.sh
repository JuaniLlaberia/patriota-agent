#!/bin/sh
# start-gateway.sh — runs on every gateway start (as patriota user).
#
# Startup sequence:
#   1. Sync skills from canonical /opt/patriota/skills/ (reverts self-improvement drift)
#   2. Wipe agent memory if a post-deploy .needs-clean flag is present
#   3. Register/update the MCP server config (picks up current env vars)
#   4. Re-seed cron jobs if sentinel is absent (idempotent: remove then create)
#   5. exec-replace with `hermes gateway`
#
# Key env vars (set in /etc/patriota/env):
#   HERMES_WORKDIR        — dir Hermes uses as workdir; AGENTS.md must live here
#   PATRIOTA_INSTALL_MCP  — path to patriota-install-mcp binary
#   PATRIOTA_SEED_DONE    — sentinel path; delete it to force a re-seed

set -eu

HERMES_WORKDIR="${HERMES_WORKDIR:-$HOME/.hermes}"
PATRIOTA_INSTALL_MCP="${PATRIOTA_INSTALL_MCP:-patriota-install-mcp}"
PATRIOTA_SEED_DONE="${PATRIOTA_SEED_DONE:-$HERMES_WORKDIR/.cron-seeded}"
CANONICAL_SKILLS="/opt/patriota/skills"

# ── 1. Sync skills ────────────────────────────────────────────────────────────
# Overwrites ~/.hermes/skills/ with the root-owned canonical copy every start.
# This reverts any self-improvement patches and removes agent-created skills.
echo "==> Sincronizando skills..."
if [ -d "$CANONICAL_SKILLS" ]; then
    rm -rf "$HERMES_WORKDIR/skills"
    cp -r "$CANONICAL_SKILLS" "$HERMES_WORKDIR/skills"
    echo "  skills sincronizadas desde $CANONICAL_SKILLS"
else
    echo "  ! $CANONICAL_SKILLS no existe — omitiendo sync (ejecutá install.sh primero)"
fi

# ── 2. Limpieza post-deploy ───────────────────────────────────────────────────
# install.sh crea .needs-clean para indicar que hay un nuevo deploy.
# Limpiamos las memorias del agente (que pueden tener estado obsoleto) y removemos la flag.
NEEDS_CLEAN="$HERMES_WORKDIR/.needs-clean"
if [ -f "$NEEDS_CLEAN" ]; then
    echo "==> Limpieza post-deploy: borrando memorias del agente..."
    rm -rf "$HERMES_WORKDIR/memory"
    rm -f "$NEEDS_CLEAN"
    echo "  memorias borradas"
fi

# ── 3. Registrar MCP ─────────────────────────────────────────────────────────
echo "==> Registrando MCP patriota-tools..."
"$PATRIOTA_INSTALL_MCP"

# ── 4. Sembrar cron jobs ──────────────────────────────────────────────────────
echo "==> Verificando cron jobs..."

if [ -f "$PATRIOTA_SEED_DONE" ]; then
    echo "  ya sembrados (eliminar $PATRIOTA_SEED_DONE para re-sembrar)"
else
    echo "  sembrando cron jobs..."

    # Idempotente: elimina el job si ya existe, luego lo crea fresco.
    _seed_cron() {
        _name="$1"; shift
        hermes cron remove "$_name" 2>/dev/null || true
        hermes cron create "$@" --name "$_name"
        echo "  seeded: $_name"
    }

    # Monitoreo continuo (Phase 3): ingesta → clustering semántico → títulos
    _seed_cron monitoreo \
        "every 45m" \
        "Ejecutá un ciclo de monitoreo editorial con la skill editorial-flow: primero corré mcp_patriota_ingest_all para ingestar nuevas fuentes, luego mcp_patriota_cluster_items_semantically para agruparlas por similitud semántica, y si se crearon clusters nuevos proponé al grupo los títulos candidatos numerados. Si no hay clusters nuevos avisá brevemente y terminá. No publiques nada; esperá la aprobación del equipo." \
        --skill editorial-flow \
        --deliver telegram \
        --workdir "$HERMES_WORKDIR"

    # Twitter diario: 09:00 ART = 12:00 UTC
    _seed_cron twitter-diario \
        "0 12 * * *" \
        "Ejecutá el ciclo diario de Twitter con la skill twitter-flow: traé tendencias (WOEID 455827), filtrá según el prompt twitter y proponé al grupo borradores de tweets numerados. No publiques sin @AgentePatriotaBot /aprobar." \
        --skill twitter-flow \
        --deliver telegram \
        --workdir "$HERMES_WORKDIR"

    # Resumen semanal: viernes 09:00 ART = 12:00 UTC
    _seed_cron resumen-semanal \
        "0 12 * * 5" \
        "Generá el resumen semanal con la skill weekly-summary y publicalo al CMS en estado borrador; avisá al grupo con el cms_id." \
        --skill weekly-summary \
        --deliver telegram \
        --workdir "$HERMES_WORKDIR"

    touch "$PATRIOTA_SEED_DONE"
    echo "  listo — re-sembrá borrando $PATRIOTA_SEED_DONE y reiniciando"
fi

# ── 5. Lanzar gateway ─────────────────────────────────────────────────────────
echo "==> Iniciando hermes gateway..."
exec hermes gateway
