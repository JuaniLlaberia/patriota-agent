#!/bin/bash
# no_agent watchdog (ejemplo): alerta si la ingesta parece detenida.
# Patrón watchdog: si todo está bien, stdout vacío = tick silencioso (sin mensaje);
# solo "habla" cuando hay un problema. Registrar con:
#   hermes cron create "every 1h" --no-agent --script source-freshness.sh \
#     --deliver telegram --name watchdog-ingesta
#
# Vive en ~/.hermes/scripts/ (copiado desde hermes/scripts/). Sin tokens LLM.

DB="${PATRIOTA_DB_PATH:-/data/patriota.db}"
MAX_AGE_MIN=120   # si la DB no se actualiza hace >2h, avisar

if [ ! -f "$DB" ]; then
  echo "⚠️ Watchdog: no encuentro la base de datos en $DB."
  exit 0
fi

now=$(date +%s)
mtime=$(stat -c %Y "$DB" 2>/dev/null || stat -f %m "$DB" 2>/dev/null)
age_min=$(( (now - mtime) / 60 ))

if [ "$age_min" -gt "$MAX_AGE_MIN" ]; then
  echo "⚠️ Watchdog: la ingesta parece detenida (sin cambios hace ${age_min} min)."
fi
# Si está fresca, no imprime nada → tick silencioso.
exit 0
