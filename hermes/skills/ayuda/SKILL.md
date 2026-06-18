---
name: ayuda
description: >
  Lista todos los comandos disponibles del agente editorial con descripción y uso.
  Invocá con /ayuda.
---

# Ayuda — comandos disponibles

Respondé con este mensaje exacto sin llamar ninguna herramienta:

```
📖 *Comandos de El Patriota*

*Flujo editorial*
/aprobar [ID ID...] — Aprobá título(s) o resumen(es). Sin ID aprueba todo lo pendiente.
/descartar [ID] — Descartá un artículo o tweet por ID.
/modificar [ID] [instrucción] — Reescribí el título o resumen de un artículo.
/publicar [ID] — Publicá al CMS un artículo con borrador listo.
/estado — Ver todo lo pendiente con sus IDs.

*Prompts editoriales*
/prompt_editorial — Ver el prompt editorial vigente.
/prompt_filtrado — Ver el prompt de filtrado vigente.
/prompt_twitter — Ver el prompt de Twitter vigente.
/editar_prompt [nombre] [nuevo texto] — Reemplazar un prompt (editorial, filtering, twitter, working_hours).

*Twitter/X*
/tweet_ahora [ID] — Publicar un tweet aprobado de inmediato.
/tweet_programado [ID] [fecha/hora] — Programar un tweet para más tarde.

*Otros*
/ayuda — Mostrar este mensaje.
```
