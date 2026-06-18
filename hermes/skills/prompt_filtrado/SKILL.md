---
name: prompt_filtrado
description: >
  Muestra el prompt de filtrado editorial vigente. Invocá con /prompt_filtrado.
---

# Ver prompt de filtrado

Llamá `mcp_patriota_get_prompt("filtering")` y mostrá el campo `content` completo:

```
📝 *Prompt de filtrado vigente*

[content]
```

Si no hay versión definida avisá: "Sin prompt de filtrado definido todavía."
