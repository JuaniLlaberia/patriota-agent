---
name: aprobar
description: >
  Aprueba título(s) propuesto(s) por ID y genera el resumen editorial correspondiente.
  Solo actúa sobre artículos en status 'title_proposed'. Invocá con /aprobar [ID ID...]
  o /aprobar (sin IDs para aprobar todos los títulos pendientes).
---

# Aprobar títulos

Extraé los IDs del mensaje en orden de aparición (ej: `/aprobar 42 44` → IDs 42 y 44).
Antes de actuar, confirmá al grupo: "Procesando artículo(s): #42, #44". Usá exactamente
los números del mensaje — nunca inferás ni ajustés un ID.

## Ciclo de vida del artículo

```
title_proposed   → [/aprobar]  → genera resumen                        → summary_proposed
summary_proposed → [/publicar] → avanza estado + genera borrador + CMS → published
published / rejected → estado terminal, no procesar
```

`/aprobar` **solo** hace la transición `title_proposed → summary_proposed`. Generar el
borrador completo y publicarlo al CMS es responsabilidad exclusiva de `/publicar` — no lo
hagas desde acá aunque el editor lo pida en el mismo mensaje; avisá que use `/publicar`.

## Obtener artículos a aprobar

- **Con IDs**: `mcp_patriota_get_article(id)` para cada uno.
- **Sin IDs**: `mcp_patriota_list_articles()` → filtrá los que tengan `status == 'title_proposed'`.

## Para cada artículo

1. Traé el artículo: `mcp_patriota_get_article(article_id)`.
   Si devuelve error o vacío, avisá "Artículo #[ID] no encontrado" y saltealo.
2. Verificá el `status`:
   - `title_proposed` → seguí con los pasos 3-6.
   - `summary_proposed` → avisá "Artículo #[ID] ya tiene resumen — usá /publicar [ID] para generar el borrador y publicar" y saltealo. **No llames a ninguna otra herramienta para este artículo.**
   - `summary_approved`, `published`, `rejected` → avisá "Artículo #[ID] ya está en [status], no requiere aprobación" y saltealo.
3. Cargá el prompt: `mcp_patriota_fetch_prompt("filtering")`.
4. Cargá las fuentes: `mcp_patriota_get_cluster(cluster_id)`.
5. Redactá el ángulo editorial (2-3 oraciones) y listá las fuentes.
6. Guardá el resumen Y avanzá el estado en una sola llamada:
   `mcp_patriota_update_article(article_id, summary=resumen_redactado, status="summary_proposed")`.
7. Enviá al grupo:
```
📋 *Resumen — Artículo #[ID]*
Título: [título]

Ángulo: [descripción del enfoque en 2-3 oraciones]

Fuentes ([N]):
• [fuente] — "[fragmento del título]" → [url]
• ...

/publicar [ID] para generar el borrador y publicar al CMS, o /modificar [ID] [instrucción] para ajustar.
```

## Reglas

- Determiná la etapa **siempre por el campo `status`**, nunca por si `summary` está vacío o no.
- Nunca llames a `mcp_patriota_publish_article_to_cms` desde este skill.
- Registrá cada aprobación: `mcp_patriota_log_editor("in", mensaje_original)`.
