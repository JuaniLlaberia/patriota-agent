# Cron jobs de Hermes — El Patriota

Crear estos jobs una vez, como usuario `patriota` en el VPS (los persiste en
`~/.hermes/cron/jobs.json`). El scheduler corre en el daemon (`hermes gateway`),
tick cada 60s. En desarrollo, forzar un ciclo con `hermes cron tick`.

> Recordatorio: cada job corre en **sesión nueva**; el prompt + las skills deben ser
> autosuficientes. `--workdir ~/.hermes` carga `AGENTS.md` (persona + reglas).

## 1) Monitoreo continuo (ingesta → clustering semántico → títulos)
Cadencia inicial 45 min (configurable, estimado 30–60). Modelo más barato para el tick rutinario.

```bash
hermes cron create "every 45m" \
  "Ejecutá un ciclo de monitoreo editorial con la skill editorial-flow: primero corré mcp_patriota_ingest_all para ingestar nuevas fuentes, luego mcp_patriota_cluster_items_semantically para agruparlas por similitud semántica. Después, con independencia de si se crearon clusters nuevos o no, listá TODOS los artículos en 'title_proposed' y envialos al grupo. No publiques nada; esperá la aprobación del equipo." \
  --name monitoreo \
  --skill editorial-flow \
  --deliver telegram \
  --workdir ~/.hermes
```

## 2) Twitter diario (tendencias → propuesta de tweets)
9:00 ART = 12:00 UTC.

```bash
hermes cron create "0 12 * * *" \
  "Ejecutá el ciclo diario de Twitter con la skill twitter-flow: traé tendencias (WOEID 455827), filtrá según el prompt twitter y proponé al grupo borradores de tweets numerados. No publiques sin @AgentePatriotaBot /aprobar." \
  --name twitter-diario \
  --skill twitter-flow \
  --deliver telegram \
  --workdir ~/.hermes
```

## 3) Resumen semanal
Viernes 09:00 ART = 12:00 UTC.

```bash
hermes cron create "0 12 * * 5" \
  "Generá el resumen semanal con la skill weekly-summary y publicalo al CMS en estado borrador; avisá al grupo con el cms_id." \
  --name resumen-semanal \
  --skill weekly-summary \
  --deliver telegram \
  --workdir ~/.hermes
```

## 4) Tweets programados (one-shot, dinámicos)
NO se crean acá. Los crea Hermes cuando un editor aprueba un tweet con horario
(ver skill twitter-flow), por ejemplo:

```bash
hermes cron create "2026-06-05T09:00:00-03:00" \
  "Publicá el tweet 42, ya aprobado: usá mcp_patriota_publish_tweet con tweet_id=42." \
  --name tweet-42 \
  --deliver telegram \
  --workdir ~/.hermes
```

## Gestión
```bash
hermes cron list
hermes cron tick                 # forzar un ciclo (dev)
hermes cron pause <nombre|id>
hermes cron resume <nombre|id>
hermes cron remove <nombre|id>
```
