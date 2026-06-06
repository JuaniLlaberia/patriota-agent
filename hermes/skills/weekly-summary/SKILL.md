---
name: weekly-summary
description: >
  Genera el resumen semanal de El Patriota con las notas más relevantes de la
  semana y lo publica al CMS en estado borrador, notificando al equipo.
---

# Resumen semanal

Armás un resumen con las notas destacadas de la semana. Español rioplatense, prompt
`editorial` vigente.

> **Criterios a definir con el cliente (Fase 1):** ventana temporal, día y hora de ejecución,
> cantidad de notas destacadas, y criterio de relevancia (tráfico del CMS, criterio editorial
> por LLM, o curaduría manual asistida). Hasta definirlo, usá: últimos 7 días, top 5 por criterio
> editorial, y dejalo explícito en el texto.

## Pasos
1. Traé las notas publicadas de la semana con `mcp_patriota_list_articles(status="published")`
   y quedate con las de la ventana acordada.
2. Seleccioná las más relevantes según el criterio definido.
3. Redactá el resumen (intro + las notas destacadas con su bajada y link).
4. Creá un artículo contenedor: `mcp_patriota_create_article(title="Resumen semanal — <fechas>")`,
   guardá el cuerpo con `mcp_patriota_update_article(..., body=...)`.
5. Publicalo como borrador con `mcp_patriota_publish_article_to_cms(article_id)`.
6. Notificá al grupo que el resumen quedó en el CMS en estado borrador (con el `cms_id`).

Se ejecuta vía el cron `resumen-semanal` (ver hermes/cron/seed-jobs.md).
