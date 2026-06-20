---
name: modificar
description: >
  Reescribe el título o resumen de un artículo siguiendo la instrucción del editor.
  Invocá con /modificar [ID] [instrucción].
---

# Modificar artículo

Extraé el ID y la instrucción del mensaje (ej: `/modificar 42 cambiar el tono a más formal`).
Antes de actuar, confirmá al grupo: "Modificando artículo #42". Usá exactamente el número
del mensaje — nunca inferás ni ajustés el ID.

1. Obtenés el artículo: `mcp_patriota_get_article(id)`.
2. Detectá qué modificar:
   - Si `summary` está vacío → modificar el **título**.
   - Si `summary` está poblado → modificar el **resumen**.
3. Cargá el prompt editorial: `mcp_patriota_fetch_prompt("editorial")`.
4. Reescribí según la instrucción del editor, respetando los criterios del prompt:
   - El título DEBE nombrar actor + acción concreta + dato noticioso.
   - Nunca describas el acto de publicar ni el medio donde apareció la noticia.
5. Guardá:
   - Título: `mcp_patriota_update_article(id, title=nuevo_titulo)`.
   - Resumen: `mcp_patriota_update_article(id, summary=nuevo_resumen)`.
6. Confirmá al grupo:
```
✏️ *Artículo #[ID] actualizado*
[nuevo título o resumen]

/aprobar [ID] para confirmar, o /modificar [ID] [instrucción] para seguir ajustando.
```
