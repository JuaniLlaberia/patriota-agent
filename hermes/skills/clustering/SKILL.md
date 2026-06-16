---
name: clustering
description: >
  Clustering semántico de ítems nuevos: embeddings text-embedding-3-small → HDBSCAN →
  validación LLM. Usar automáticamente después de cada ciclo de ingesta.
---

# Clustering semántico

Agrupás automáticamente los ítems nuevos en clusters editoriales usando embeddings y validación LLM.

## Cuándo usarla
Después de cada ciclo de ingesta (`mcp_patriota_ingest_all`), antes de proponer títulos.
El cron de monitoreo la dispara automáticamente.

## Pasos
1. Llamá `mcp_patriota_cluster_items_semantically` (sin argumentos para procesar todos los ítems nuevos y solo).
2. Evaluá el resultado:
   - Si `clusters_created > 0`: reportá al grupo cuántos clusters se crearon y cuántos ítems quedaron sin cluster, luego iniciá la skill `editorial-flow` para proponer títulos.
   - Si `clusters_created == 0` y `noise_items > 0`: avisá al grupo ("Material ingresado pero sin suficientes fuentes por tema para agrupar — se reintentará en el próximo ciclo") y terminá.
   - Si `note` indica sin ítems nuevos: avisá al grupo y terminá.

## Reglas
- No llamés a `create_cluster` manualmente; eso lo hace la herramienta.
- Los ítems sin cluster quedan en estado `solo` y se reintentan en el próximo ciclo automáticamente.
- Si la herramienta falla por falta de API keys, reportá el error al grupo con el mensaje exacto.
