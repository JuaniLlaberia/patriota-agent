---
name: generacion
description: >
  Motor de dos prompts para generar borradores completos de artículos.
  Se activa después de que el editor aprueba el resumen de un artículo.
---

# Generación de borradores

Generás el borrador completo de un artículo usando el pipeline de dos prompts (generación → rechequeo).

## Cuándo usarla
Cuando un artículo pasa a estado `summary_approved` — ya sea por `/aprobar` del editor
o por aprobación en la skill `editorial-flow`.

## Pasos
1. Recibís el `article_id` del artículo en estado `summary_approved`.
2. Llamá `mcp_patriota_generate_article_draft(article_id)`.
3. Si la generación fue exitosa: mostrá al grupo el título y la bajada del borrador generado para revisión rápida.
4. Confirmá que el borrador está listo para publicar y coordiná con la skill `publicador-cms`.

## En caso de error
- Si falla por timeout (30s × 2 intentos): avisá al grupo, esperá confirmación para reintentar.
- Si falla por API key faltante: reportá el error exacto y pedí al administrador que configure la variable.

## Reglas
- Solo operás sobre artículos en `status='summary_approved'`.
- No edités el contenido generado directamente; si el editor pide cambios, el agente usa `/modificar` en `editorial-flow` para regenerar.
- El borrador nunca se publica automáticamente; siempre pasa por `publicador-cms` con aprobación previa.
