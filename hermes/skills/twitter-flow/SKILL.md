---
name: twitter-flow
description: >
  Propuesta diaria de contenido para X/Twitter de El Patriota: tendencias de
  Argentina → filtrado editorial → borradores de tweets numerados → aprobación →
  publicación inmediata o programada. Usar para el ciclo de redes.
---

# Flujo de Twitter/X

Proponés tweets para *El Patriota* con **aprobación humana** antes de publicar. Español
rioplatense. Cargá primero el prompt vigente con `mcp_patriota_get_prompt("twitter")` y seguí
sus criterios de selección de tendencias, tono y posición editorial.

## Paso 1 — Tendencias y filtrado
1. Traé tendencias con `mcp_patriota_get_trends` (Argentina/Buenos Aires, WOEID 455827).
2. Filtrá según el prompt `twitter` (temas relevantes para El Patriota; descartá lo que no aplica).
3. Para profundizar un tema podés usar `mcp_patriota_search_twitter(query)`.

## Paso 2 — Borradores numerados
1. Para cada tema relevante, redactá un borrador de tweet con el tono y la posición del medio.
2. Registralo con `mcp_patriota_propose_tweet(text)` (queda `proposed`).
3. Enviá al grupo la lista **numerada** con el `tweet_id` de cada uno.
4. Feedback:
   - Cambios por número → reescribí; registrá el nuevo texto con un `propose_tweet` y descartá el viejo, o aclarálo.
   - `/aprobar` → seguí al Paso 3.

## Paso 3 — Publicar o programar
- **Inmediato:** `mcp_patriota_approve_tweet(tweet_id)` y luego `mcp_patriota_publish_tweet(tweet_id)`.
- **Programado** (ej. "publicar mañana a las 9:00"):
  1. Calculá la fecha/hora exacta en **ISO 8601** (zona horaria de Argentina).
  2. `mcp_patriota_approve_tweet(tweet_id, scheduled_at="2026-06-05T09:00:00-03:00")` → queda `scheduled`.
  3. Creá un **cron one-shot** de Hermes en ese mismo ISO timestamp cuyo prompt sea, por ejemplo:
     `"Publicá el tweet 42 ya aprobado: usá la herramienta mcp_patriota_publish_tweet con tweet_id=42."`
     (incluí todo lo necesario; los cron jobs corren en sesión nueva).
- Confirmá al grupo el resultado (`external_id` o el horario programado).

## Reglas
- Nunca publiques un tweet sin `/aprobar`.
- Mantené el límite de caracteres de X.
- Para el ciclo diario automático, este skill se invoca desde el cron `twitter-diario`
  (ver hermes/cron/seed-jobs.md): proponés y entregás al grupo; la aprobación sigue siendo humana.
