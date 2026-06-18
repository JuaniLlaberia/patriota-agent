---
name: publicar
description: >
  Publica al CMS un artículo que ya tiene borrador generado. Requiere /aprobar previo.
  Invocá con /publicar [ID].
---

# Publicar artículo al CMS

Extraé el ID del mensaje (ej: `/publicar 42`).

1. Obtenés el artículo: `mcp_patriota_get_article(id)`.
2. Si no tiene `body` (borrador): avisá "El artículo #[ID] no tiene borrador generado. Usá /aprobar [ID] primero."
3. Si tiene `body`: publicá al CMS: `mcp_patriota_publish_article_to_cms(id)`.
4. Confirmá al grupo:
```
✅ *Artículo #[ID] publicado*
Título: [título]
CMS ID: [cms_id]
```
5. Registrá: `mcp_patriota_log_editor("out", confirmación)`.
