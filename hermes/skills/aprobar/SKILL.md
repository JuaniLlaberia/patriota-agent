---
name: aprobar
description: >
  Aprueba título(s) o resumen(es) de artículos por ID. Detecta automáticamente la etapa
  de cada artículo y ejecuta la acción correcta. Invocá con /aprobar [ID ID...] o /aprobar.
---

# Aprobar artículos

Extraé los IDs del mensaje (ej: `/aprobar 42 44` → IDs 42 y 44). Sin IDs, procesá todos
los artículos con `status='title_proposed'`.

## Obtener artículos a aprobar

- **Con IDs**: `mcp_patriota_get_article(id)` para cada uno.
- **Sin IDs**: `mcp_patriota_list_articles(status="title_proposed")` → todos los pendientes.

## Para cada artículo — detectar etapa y actuar

### Etapa A — el campo `summary` está vacío: aprobación de título

El editor aprobó el título. Generá el resumen editorial:

1. Cargá el prompt: `mcp_patriota_fetch_prompt("filtering")`.
2. Cargá las fuentes: `mcp_patriota_get_cluster(cluster_id)`.
3. Redactá el ángulo editorial (2-3 oraciones) y listá las fuentes.
4. Guardá el resumen: `mcp_patriota_update_article(article_id, summary=resumen_redactado)`.
5. Enviá al grupo:
```
📋 *Resumen — Artículo #[ID]*
Título: [título]

Ángulo: [descripción del enfoque en 2-3 oraciones]

Fuentes ([N]):
• [fuente] — "[fragmento del título]" → [url]
• ...

/aprobar [ID] para generar el borrador, o /modificar [ID] [instrucción] para ajustar.
```

### Etapa B — el campo `summary` está poblado: aprobación de resumen

El editor aprobó el resumen. Generá el borrador completo:

1. Actualizá el estado: `mcp_patriota_update_article(article_id, status="summary_approved")`.
2. Generá el borrador: `mcp_patriota_generate_article_draft(article_id)`.
3. Confirmá al grupo:
```
✅ *Borrador generado — Artículo #[ID]*
Título: [título]
Bajada: [bajada generada]

Usá /publicar [ID] para publicar al CMS cuando estés listo.
```

## Reglas

- No publiques al CMS desde este skill; eso lo hace /publicar.
- Si el artículo ya está `published` o `rejected`: avisá y saltéalo.
- Si `generate_article_draft` falla: avisá el error exacto y dejá el artículo en `summary_approved` para reintentar.
- Registrá cada aprobación: `mcp_patriota_log_editor("in", mensaje_original)`.
