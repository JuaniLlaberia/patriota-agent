---
name: prompt_filtrado
description: >
  Muestra el prompt de filtrado editorial vigente. Invocá con /prompt_filtrado.
---

# Ver prompt de filtrado

Llamá `mcp_patriota_fetch_prompt("filtering")` y mostrá el campo `content` completo.

Si el campo `note` contiene "default" agregá un aviso al pie: _"(usando versión predeterminada — podés personalizarlo con /editar_prompt filtering)"_.

```
📝 *Prompt de filtrado vigente*

[content]
```
