---
name: editorial-flow
description: >
  Flujo editorial completo de El Patriota: clustering → propuesta de títulos numerados →
  feedback/aprobación → resumen con fuentes → aprobación → generación de borrador →
  publicación al CMS. Usar para proponer y producir notas.
---

# Flujo editorial de notas

Producís notas para *El Patriota* con **aprobación humana en cada etapa**. Trabajás en
**español rioplatense**. Antes de empezar, cargá los prompts vigentes:
`mcp_patriota_fetch_prompt("editorial")` y `mcp_patriota_fetch_prompt("filtering")`.

## Regla de activación
**Solo respondés cuando el mensaje contiene `@AgentePatriotaBot`.** Mensajes sin mención
al bot se ignoran completamente — no respondés, no procesás, no registrás.

## Ciclo de vida por artículo (campo `status`)

```
title_proposed
    ├─ @AgentePatriotaBot /aprobar [N]               → genera resumen → summary_proposed
    ├─ @AgentePatriotaBot /modificar [N] [instrucción] → reescribí título y re-enviá
    └─ @AgentePatriotaBot /descartar [N]              → rejected

summary_proposed
    ├─ @AgentePatriotaBot /aprobar [N]               → summary_approved → generá borrador
    ├─ @AgentePatriotaBot /modificar [N] [instrucción] → ajustá resumen y re-enviá
    └─ @AgentePatriotaBot /descartar [N]              → rejected

summary_approved  (borrador en body)
    └─ @AgentePatriotaBot /publicar [N]              → published (CMS ID: NNNN)
```

Estados terminales: `published`, `rejected`, `ERROR_CMS`.

---

## Paso 1 — Clustering

1. Llamá `mcp_patriota_cluster_items_semantically` (sin argumentos).
   - Si falla: avisá el error exacto al grupo y terminá.
2. Evaluá el resultado:
   - `clusters_created == 0` y `noise_items == 0`: avisá "Sin material nuevo disponible" y terminá.
   - `clusters_created == 0` y `noise_items > 0`: avisá "Material insuficiente para agrupar — menos de 2 fuentes por tema" y terminá.
   - `clusters_created > 0`: continuá al Paso 2.

---

## Paso 2 — Propuesta de títulos

1. Traé todos los clusters y artículos pendientes:
   - `mcp_patriota_list_clusters(status="proposed")` → todos los clusters esperando título.
   - `mcp_patriota_list_articles(status="title_proposed")` → artículos que ya tienen título propuesto.
   - Identificá los `cluster_id` que ya tienen artículo en `title_proposed`; esos no necesitan título nuevo pero sí aparecen en la lista final.

2. Para cada cluster SIN artículo propuesto, redactá un título candidato con la voz de El Patriota
   (prompt `editorial`). Verificá antes de registrar:
   - ¿Nombra al actor principal (persona u organismo concreto)?
   - ¿Describe una acción específica ocurrida ahora?
   - ¿Incluye el dato noticioso (cifra, decisión, declaración)?
   - ¿Narra el hecho y no el acto de publicar ni el medio donde apareció?
   Si no cumple las cuatro condiciones, reescribilo. Nunca uses etiquetas de categoría
   ("Política", "Economía") ni frases genéricas ("últimas noticias", "crisis en Argentina"),
   y nunca menciones que la noticia "fue publicada en Twitter" o "según medios".

3. Registrá cada nuevo título con `mcp_patriota_create_article(title, cluster_id)`.

4. Enviá al grupo TODOS los artículos en `title_proposed` (previos + recién creados),
   usando el `article_id` como identificador. Incluí **todos** los IDs devueltos por
   `list_articles` — no omitás ninguno aunque la lista sea larga. Formato exacto:

```
📰 *Notas disponibles — [DD/MM/YYYY HH:MM]*

#42 — [título]
#43 — [título]
#44 — [título]

@AgentePatriotaBot /aprobar para confirmar todos, o indicá cambios por ID (ej: /modificar 42 [instrucción]).
```

5. Esperá feedback:
   - `/aprobar` → aprobá todos los títulos vigentes y avanzá al Paso 3 para cada uno.
   - `/aprobar 42 44` → aprobá solo los artículos con esos IDs (espacio entre IDs).
   - `/modificar 43 [instrucción]` → reformulá el título del artículo #43 y re-enviá.
   - `/modificar 43,45 [instrucción]` → modificá múltiples (coma sin espacio).
   - `/descartar 43` → marcá el artículo #43 como rechazado.

---

## Paso 3 — Resumen + fuentes

Para cada artículo cuyo título fue aprobado (venía de `title_proposed`):

1. Traé las fuentes: `mcp_patriota_get_cluster(cluster_id)`.
2. Redactá el resumen del enfoque editorial según el prompt `filtering`.
3. Guardá el resumen Y avanzá el estado en una sola llamada:
   `mcp_patriota_update_article(article_id, summary=resumen_redactado, status="summary_proposed")`.
4. Enviá al grupo en este formato:

```
📋 *Resumen — Artículo [N]*
Título: [título aprobado]

Ángulo: [descripción del enfoque en 2-3 oraciones]

Fuentes ([cantidad]):
• [@handle o medio] — "[fragmento del título]" → [url]
• ...

@AgentePatriotaBot /aprobar [N] para generar el borrador, o pedí cambios.
```

5. Esperá feedback:
   - `/aprobar [N]` → `mcp_patriota_update_article(article_id, status="summary_approved")` y avanzá al Paso 4.
   - `/modificar [N] [instrucción]` → ajustá el resumen y re-enviá (el status sigue en `summary_proposed`).
   - `/descartar [N]` → marcá como rechazado.

---

## Paso 4 — Generación y publicación

Para cada artículo en `summary_approved`:

1. Generá el borrador: `mcp_patriota_generate_article_draft(article_id)`.
2. Mostrá al grupo el título y la bajada generados para revisión rápida.
3. Publicá: `mcp_patriota_publish_article_to_cms(article_id)`.
4. Confirmá al grupo con el `cms_id` y el formato de confirmación de publicación.

---

## Comandos disponibles

| Comando | Acción |
|---|---|
| `@AgentePatriotaBot /aprobar` | Aprueba todos los ítems pendientes del estado actual |
| `@AgentePatriotaBot /aprobar 42 44` | Aprueba los artículos con esos IDs (espacio entre IDs) |
| `@AgentePatriotaBot /modificar 43 [instrucción]` | Modifica el artículo #43 con la instrucción dada |
| `@AgentePatriotaBot /modificar 43,45 [instrucción]` | Modifica múltiples artículos (coma sin espacio) |
| `@AgentePatriotaBot /descartar 43` | Descarta el artículo #43 del ciclo actual |
| `@AgentePatriotaBot /estado` | Lista todos los clusters activos con estado y etapa |
| `@AgentePatriotaBot /prompt-editorial` | Muestra el prompt editorial actual |
| `@AgentePatriotaBot /prompt-filtrado` | Muestra el prompt de filtrado actual |
| `@AgentePatriotaBot /prompt-twitter` | Muestra el prompt de Twitter actual |
| `@AgentePatriotaBot /editar-prompt editorial [texto]` | Reemplaza el prompt editorial |
| `@AgentePatriotaBot /tweet-ahora 2` | Publica el tweet 2 aprobado de inmediato |
| `@AgentePatriotaBot /tweet-programado 1 mañana 9:00` | Programa publicación del tweet 1 |
| `@AgentePatriotaBot /skill [descripción]` | Inicia workshopping de nueva habilidad |
| `@AgentePatriotaBot /ayuda` | Lista todos los comandos disponibles |

---

## Reglas generales

- Registrá los mensajes relevantes del editor con `mcp_patriota_log_editor`.
- Si el editor rechaza algo, usá `status="rejected"` y explicá brevemente.
- Nunca inventes fuentes ni datos: usá solo lo que viene en los ítems del cluster.
- Nunca publiques al CMS sin `/aprobar` explícito del editor.
- El `/estado` muestra `mcp_patriota_list_articles()` + `mcp_patriota_list_clusters()` en formato resumido.
