---
name: editar_prompt
description: >
  Reemplaza el contenido de un prompt editorial. Guarda la nueva versión con trazabilidad.
  Invocá con /editar_prompt [nombre] [nuevo texto completo].
---

# Editar prompt editorial

Extraé el nombre del prompt y el nuevo contenido del mensaje.
Formato esperado: `/editar_prompt [nombre] [texto completo del nuevo prompt]`

Nombres válidos: `editorial`, `filtering`, `twitter`, `working_hours`.

Para `working_hours` el formato del contenido debe ser `HH:MM-HH:MM` (ej: `07:00-00:00`).

1. Verificá que el nombre sea uno de los válidos. Si no: "Nombre de prompt no reconocido. Válidos: editorial, filtering, twitter, working_hours."
2. Guardá: `mcp_patriota_set_prompt(nombre, contenido, editor="telegram")`.
3. Confirmá:
```
✅ *Prompt '[nombre]' actualizado*
Nueva versión guardada. Los cambios se aplican en el próximo ciclo.
```
