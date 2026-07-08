---
name: aprobar
description: >
  Aprueba artículos por ID avanzando su estado en el ciclo editorial.
  Detecta la etapa por el campo status y ejecuta la acción correcta.
  Invocá con /aprobar [ID ID...] o /aprobar (sin IDs para aprobar todo lo pendiente).
---

# Aprobar artículos

Extraé los IDs del mensaje en orden de aparición (ej: `/aprobar 42 44` → IDs 42 y 44).
Antes de actuar, confirmá al grupo: "Procesando artículo(s): #42, #44". Usá exactamente
los números del mensaje — nunca inferás ni ajustés un ID.

## Ciclo de vida del artículo

```
title_proposed   → [/aprobar] → genera resumen → summary_proposed
summary_proposed → [/aprobar] → avanza estado + genera borrador → summary_approved
summary_approved → (borrador listo) → /publicar [ID]
published / rejected → estado terminal, no procesar
```

## Obtener artículos a aprobar

- **Con IDs**: `mcp_patriota_get_article(id)` para cada uno.
- **Sin IDs**: `mcp_patriota_list_articles()` → filtrá los que tengan
  `status == 'title_proposed'` o `status == 'summary_proposed'`.

## Para cada artículo — detectar etapa por el campo status

### Etapa A — status == 'title_proposed': aprobación de título

El editor aprobó el título propuesto. Generá el resumen editorial:

1. Cargá el prompt: `mcp_patriota_fetch_prompt("filtering")`.
2. Cargá las fuentes: `mcp_patriota_get_cluster(cluster_id)`.
3. Redactá el ángulo editorial (2-3 oraciones) y listá las fuentes.
4. Guardá el resumen Y avanzá el estado en una sola llamada:
   `mcp_patriota_update_article(article_id, summary=resumen_redactado, status="summary_proposed")`.
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

### Etapa B — status == 'summary_proposed': aprobación de resumen

El editor aprobó el resumen. Avanzá el estado y generá el borrador:

1. Verificá que el artículo existe: `mcp_patriota_get_article(article_id)`.
   Si devuelve error o vacío, avisá "Artículo #[ID] no encontrado" y detenete.
2. Avanzá el estado: `mcp_patriota_update_article(article_id, status="summary_approved")`.
   **Este paso debe completarse exitosamente antes de continuar.**
3. Generá el borrador: `mcp_patriota_generate_article_draft(article_id)`.
4. Confirmá al grupo:
```
✅ *Borrador generado — Artículo #[ID]*
Título: [título]
Bajada: [bajada generada]

Usá /publicar [ID] para publicar al CMS cuando estés listo.
```

## Reglas

- Determiná la etapa **siempre por el campo `status`**, nunca por si `summary` está vacío o no.
- No publiques al CMS desde este skill; eso lo hace /publicar.
- Si el artículo está en `summary_approved`, `published` o `rejected`: avisá y saltéalo.
- Si `generate_article_draft` falla: avisá el error exacto. No reintentes en loop;
  el artículo queda en `summary_approved` y el editor puede reintentar con /publicar.
- Registrá cada aprobación: `mcp_patriota_log_editor("in", mensaje_original)`.
