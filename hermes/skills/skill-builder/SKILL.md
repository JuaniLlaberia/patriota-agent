---
name: skill-builder
description: >
  Workshopping colaborativo de nuevas habilidades con el equipo editorial. Hermes
  dialoga, redacta una SKILL.md candidata y la deja PENDIENTE de revisión del
  desarrollador. Nunca activa skills nuevas por su cuenta.
---

# Construcción colaborativa de skills

Cuando el equipo necesita que Hermes haga algo nuevo, lo trabajás con ellos por Telegram.

## Procedimiento
1. **Dialogá** para entender bien el requerimiento (qué, cuándo, con qué fuentes, qué salida).
2. **Redactá** una SKILL.md candidata: frontmatter (`name`, `description`) + instrucciones en
   lenguaje natural, reutilizando las herramientas `mcp_patriota_*` existentes cuando se pueda.
3. **Mostrásela** al grupo y **iterá** según el feedback.
4. Cuando el equipo la aprueba, **guardá el borrador para revisión** y avisá:
   - Escribí el archivo candidato en `hermes/skills/_pending/<name>/SKILL.md`
     (carpeta `_pending`, NO en la raíz de skills).
   - Notificá al grupo: *"La skill quedó lista y pendiente de revisión técnica del desarrollador."*

## Regla crítica — activación supervisada
**Nunca** instales ni actives una skill nueva en producción por tu cuenta, aunque el equipo la
haya aprobado en Telegram. La activación (mover de `_pending/` a la carpeta de skills activas) la
hace el desarrollador tras la revisión técnica. Esto protege la integridad del sistema (§2.4 de la
propuesta).
