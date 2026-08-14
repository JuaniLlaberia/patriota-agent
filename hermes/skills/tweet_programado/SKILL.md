---
name: tweet_programado
description: >
  Programa un tweet para publicar en una fecha y hora específica (zona horaria Argentina).
  Invocá con /tweet_programado [ID] [fecha/hora].
---

# Programar tweet

Extraé el ID y la fecha/hora del mensaje (ej: `/tweet_programado 12 mañana 9:00`).

1. Convertí la fecha/hora a ISO 8601 con zona horaria argentina (UTC-3).
   Ejemplo: "mañana 9:00" → `2026-06-14T09:00:00-03:00`. Calculá la fecha exacta.
2. Buscá el tweet: `mcp_patriota_list_tweets()`, filtrá por el ID.
3. Si no existe: "No encontré el tweet #[ID]."
4. Aprobá y programá: `mcp_patriota_approve_tweet(tweet_id, scheduled_at="[ISO timestamp]")`.
5. Creá un cron one-shot de Hermes en ese mismo ISO timestamp con el prompt:
   `"Publicá el tweet [ID] ya programado: ejecutá mcp_patriota_publish_tweet con tweet_id=[ID]."`
6. Confirmá al grupo:
```
⏰ *Tweet #[ID] programado*
[texto del tweet]
Publicación: [fecha/hora legible en horario argentino]
```
