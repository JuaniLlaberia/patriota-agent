---
name: publicar
description: >
  Aprueba el resumen de un artículo, genera el borrador completo y lo publica al CMS
  en un solo paso atómico. Requiere que el artículo tenga /aprobar previo (status
  summary_proposed). Invocá con /publicar [ID ID...] o /publicar (sin IDs para todos
  los pendientes en summary_proposed).
---

# Publicar artículo (aprobar resumen + generar borrador + CMS)

Extraé los IDs del mensaje en orden de aparición (ej: `/publicar 42` → ID 42). Antes de
actuar, confirmá al grupo: "Procesando artículo(s): #42". Usá exactamente los números del
mensaje — nunca inferás ni ajustés un ID.

## Qué hace `mcp_patriota_publish_article_to_cms`

Es una única herramienta atómica que hace todo el trabajo server-side — vos solo la
llamás y reportás el resultado, **no** orquestás los pasos internos ni llamás otras
herramientas de generación:

1. Verifica que el artículo esté en `summary_proposed` o `summary_approved` (este último
   es el estado de reintento — ver abajo). Si está en `title_proposed`, `published` o
   `rejected`, devuelve error.
2. Avanza el estado a `summary_approved`.
3. Genera el borrador completo (pipeline de dos prompts) con el título aprobado y las
   fuentes del cluster.
4. Publica al CMS como borrador (`visible=0`).
5. Marca el artículo `published` con su `cms_id`.

Es reintentable: si el CMS falla después de generar el borrador, el artículo queda en
`summary_approved` con el borrador ya guardado — llamar la herramienta de nuevo salta la
regeneración y solo reintenta el POST al CMS.

## Para cada ID

1. Obtenés el artículo: `mcp_patriota_get_article(id)`.
   Si no existe, avisá "Artículo #[ID] no encontrado" y saltealo.
2. Si `status` es `title_proposed`: avisá "Artículo #[ID] todavía no tiene resumen — usá /aprobar [ID] primero" y saltealo.
3. Si `status` es `published` o `rejected`: avisá "Artículo #[ID] ya está en [status]" y saltealo.
4. Si `status` es `summary_proposed` o `summary_approved`: llamá `mcp_patriota_publish_article_to_cms(id)`.
5. **Si devuelve `ok: true`:**
```
✅ *Publicado al CMS — Artículo #[ID]*
Título: [titulo]
Bajada: [bajada]
CMS ID: [cms_id]
Estado: borrador (visible: 0)
```
6. **Si devuelve `error`:** avisá el error exacto al grupo. Si el mensaje indica que el
   borrador quedó guardado (`summary_approved`), aclará que se puede reintentar con
   `/publicar [ID]` sin perder el trabajo ya generado. No reintentes en loop vos mismo.
7. Registrá: `mcp_patriota_log_editor("out", confirmación_o_error)`.
