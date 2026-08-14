---
name: descartar
description: >
  Descarta un artículo o tweet por ID, marcándolo como rechazado en la base de datos.
  Invocá con /descartar [ID].
---

# Descartar artículo o tweet

Extraé el ID del mensaje (ej: `/descartar 42`).

1. Intentá obtener el artículo: `mcp_patriota_get_article(id)`.
   - Si existe → `mcp_patriota_update_article(id, status="rejected")`.
   - Confirmá: "🗑 Artículo #[ID] descartado."

2. Si no existe como artículo, buscá en tweets: `mcp_patriota_list_tweets()`, filtrá por el ID.
   - Si existe → `mcp_patriota_reject_tweet(id)`.
   - Confirmá: "🗑 Tweet #[ID] descartado."

3. Si no existe en ninguno: "No encontré ningún artículo ni tweet con ID #[ID]."

4. Registrá: `mcp_patriota_log_editor("in", mensaje_original)`.
