---
name: prompt_editorial
description: >
  Muestra el prompt editorial vigente. Invocá con /prompt_editorial.
---

# Ver prompt editorial

Llamá `mcp_patriota_get_prompt("editorial")` y mostrá el campo `content` completo.

Si el campo `note` contiene "default" agregá un aviso al pie: _"(usando versión predeterminada — podés personalizarlo con /editar_prompt editorial)"_.

```
📝 *Prompt editorial vigente*

[content]
```
