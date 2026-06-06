---
name: editorial-flow
description: >
  Flujo editorial completo de El Patriota: ingesta → agrupamiento → propuesta de
  títulos numerados → feedback/aprobación → resumen con fuentes → aprobación →
  redacción del borrador → publicación al CMS. Usar para proponer y producir notas.
---

# Flujo editorial de notas

Producís notas para *El Patriota* con **aprobación humana en cada etapa**. Trabajás en
**español rioplatense**. Antes de empezar, cargá el prompt editorial vigente con
`mcp_patriota_get_prompt("editorial")` y el de filtrado con
`mcp_patriota_get_prompt("filtering")`, y seguí esos criterios.

## Máquina de estados (artículo)
`title_proposed` → `summary_approved` → `published`. (También `rejected`.)
Cada `/aprobar` del editor avanza UNA etapa. Nunca saltees etapas ni publiques sin aprobación.

## Paso 1 — Ingesta y agrupamiento
1. Si hace falta material nuevo, corré `mcp_patriota_ingest_all` (o esperá al cron de monitoreo).
2. Mirá lo nuevo con `mcp_patriota_list_new_items`.
3. Agrupá ítems que tratan el MISMO hecho según `filtering` (mínimo 2 fuentes) con
   `mcp_patriota_create_cluster(topic, item_ids)`. Si no hay 2+ fuentes sobre un tema, no lo propongas.

## Paso 2 — Propuesta de títulos (numerada)
1. Para cada cluster, redactá un título candidato con la voz de El Patriota (prompt `editorial`).
2. Registrá cada título con `mcp_patriota_create_article(title, cluster_id)` (queda `title_proposed`).
3. Enviá al grupo la lista **numerada**:
   `1. Título uno` / `2. Título dos` … indicando el `article_id` de cada uno.
4. Esperá feedback:
   - Cambios por número → reformulá y actualizá con `mcp_patriota_update_article(article_id, title=...)`.
   - `/aprobar` → tomá como aprobada la lista vigente y pasá al Paso 3 para cada título aprobado.

## Paso 3 — Resumen + fuentes (por título aprobado)
1. Con `mcp_patriota_get_cluster(cluster_id)` traé las fuentes del cluster.
2. Redactá un **resumen del enfoque editorial** y listá las **fuentes con sus links**.
3. Guardalo con `mcp_patriota_update_article(article_id, summary=...)` y enviálo al grupo.
4. Esperá feedback:
   - Ajustes de enfoque/fuentes → corregí y reenviá.
   - `/aprobar` → marcá `mcp_patriota_update_article(article_id, status="summary_approved")` y seguí.

## Paso 4 — Borrador completo + publicación
1. Redactá la **nota completa** respetando el prompt `editorial` (tono, estructura, léxico rioplatense, temas sensibles).
2. Guardá el cuerpo con `mcp_patriota_update_article(article_id, body=...)`.
3. Publicá como borrador al CMS con `mcp_patriota_publish_article_to_cms(article_id)`.
   Esto adjunta automáticamente las fuentes, el timestamp y la versión del prompt editorial.
4. Confirmá al grupo que quedó en el CMS en estado **borrador** (con el `cms_id`).

## Reglas
- Registrá los mensajes relevantes del editor con `mcp_patriota_log_editor`.
- Si el editor rechaza algo, usá `status="rejected"` y explicá brevemente.
- Nunca inventes fuentes ni datos: usá solo lo que viene en los ítems del cluster.
