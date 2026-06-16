---
name: publicador-cms
description: >
  Publica borradores aprobados al CMS de El Patriota vía OAuth v1.1.
  Siempre en estado borrador (visible=0). Nunca publicar sin aprobación explícita.
---

# Publicador CMS

Publicás borradores al CMS después de aprobación editorial completa del borrador generado.

## Cuándo usarla
Después de que el agente generó el borrador con `generacion` y el editor aprobó publicar
(a través del flujo `editorial-flow`).

## Pasos
1. Verificá que el artículo tenga `body` generado (llamá `mcp_patriota_get_article(article_id)` para confirmarlo).
2. Llamá `mcp_patriota_publish_article_to_cms(article_id)`.
3. **En caso de éxito:** enviá al grupo la confirmación con este formato:

```
✅ *Publicado al CMS — ID: [cms_id]*

Título: [título]
Estado: borrador (visible: 0)
```

4. **En caso de error:** la herramienta ya reintenta automáticamente después de 60s. Si el segundo intento también falla, enviá al grupo:

```
⚠️ *Error al publicar al CMS — Artículo [N]*

Error: [mensaje_error_exacto]
El borrador está guardado en la base. Podés reintentar con @AgentePatriotaBot /publicar [N]
```

Y pegá el texto del borrador en el grupo para que el equipo pueda publicarlo manualmente si es urgente.

## Reglas
- `visible` es siempre 0. La herramienta lo fuerza; no hay forma de cambiarlo desde acá.
- El token OAuth se renueva automáticamente; no necesitás intervenir.
- Si el CMS devuelve error de validación de campos, reportá el detalle exacto del campo que falló.
