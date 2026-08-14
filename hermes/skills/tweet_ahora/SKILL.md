---
name: tweet_ahora
description: >
  Publica un tweet propuesto de inmediato sin programar. Invocá con /tweet_ahora [ID].
---

# Publicar tweet ahora

Extraé el ID del tweet del mensaje (ej: `/tweet_ahora 12`).

1. Buscá el tweet: `mcp_patriota_list_tweets()`, filtrá por el ID recibido.
2. Si no existe: "No encontré el tweet #[ID]."
3. Si existe y está en estado `proposed`: aprobálo primero: `mcp_patriota_approve_tweet(tweet_id)`.
4. Publicá: `mcp_patriota_publish_tweet(tweet_id)`.
5. Confirmá al grupo:
```
🐦 *Tweet #[ID] publicado*
[texto del tweet]
```
