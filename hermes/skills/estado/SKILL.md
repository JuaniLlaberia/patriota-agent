---
name: estado
description: >
  Muestra el estado actual del pipeline editorial: artículos pendientes por etapa,
  clusters sin título, tweets propuestos. Invocá con /estado.
---

# Estado del pipeline editorial

Consultá la base de datos y mostrá un resumen del estado actual.

1. `mcp_patriota_list_articles()` → todos los artículos activos.
2. `mcp_patriota_list_clusters(status="proposed")` → clusters sin título todavía.
3. `mcp_patriota_list_tweets(status="proposed")` → tweets pendientes de aprobación.

Mostrá el resultado en este formato (omití las secciones que estén vacías):

```
📊 *Estado editorial — [DD/MM/YYYY HH:MM]*

📰 ARTÍCULOS PENDIENTES DE TÍTULO
#42 — [título]
#43 — [título]

📋 ARTÍCULOS PENDIENTES DE RESUMEN
#44 — [título] (resumen generado, esperando /aprobar 44)

✅ BORRADORES LISTOS PARA PUBLICAR
#45 — [título] → /publicar 45

🗂 CLUSTERS SIN TÍTULO: N cluster(s) esperando el próximo ciclo editorial.

🐦 TWEETS PROPUESTOS
#12 — [texto del tweet]
```

Para clasificar artículos:
- `status='title_proposed'` con `summary` vacío → pendiente de título
- `status='title_proposed'` con `summary` poblado → pendiente de resumen
- `status='summary_approved'` con `body` poblado → borrador listo para /publicar
- `status='published'` o `'rejected'` → no mostrar
