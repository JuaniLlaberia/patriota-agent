### Setup agent model

docker compose run --rm hermes model

### Run chat

docker compose run --rm hermes chat

### Env variables

```
ANTHROPIC_API_KEY=
PATRIOTA_DB_PATH=
PATRIOTA_WOEID=
TWITTERAPI_IO_KEY=
CMS_BASE_URL=
CMS_API_TOKEN=
TELEGRAM_BOT_TOKEN=
TELEGRAM_HOME_CHANNEL=
```

---

## Estado del proyecto — dónde estamos (handoff)

**Qué es.** Agente editorial autónomo de _El Patriota_ (diario digital argentino) construido
**sobre [Hermes Agent](https://hermes-agent.nousresearch.com/)** (Nous Research, MIT). No
reimplementamos el runtime: Hermes aporta el loop, memoria, skills, cron y Telegram; nosotros
aportamos las _capacidades de dominio_ como un servidor MCP (`patriota-tools`) + skills + cron.
LLM = Claude (Anthropic). Opera en español rioplatense, con `/aprobar` humano antes de publicar.

### ✅ Funciona hoy (verificado)

- **Chat + identidad de El Patriota** contra la imagen real `nousresearch/hermes-agent`. La persona
  viene de `hermes/AGENTS.md` (Hermes la auto-inyecta desde el workdir `/opt/data`). Arranca con los
  2 comandos de arriba (`model` o `config set model ...`, luego `chat`).
- **Servidor MCP `patriota-tools`** — código Python **real y funcional** (no placeholder): ~25 tools
  (`mcp_patriota_*`) sobre SQLite. Cubre ingesta + dedup, clustering (mín 2 fuentes), pipeline de
  notas (`title_proposed → summary_approved → published`), pipeline de tweets, versionado de prompts
  y trazabilidad (fuentes + timestamp + versión de prompt). 9 tests pasan; `scripts/demo_flow.py`
  corre el flujo punta a punta.

### 🟡 Mockeado (sólo el borde de I/O externa)

Cada servicio externo está detrás de una interfaz ABC con dos implementaciones, elegidas por
`USE_MOCKS`. **La lógica de las tools es real; sólo se reemplaza la llamada externa.**

| Adapter      | Mock (ahora)                                     | Real (Fase F)                    |
| ------------ | ------------------------------------------------ | -------------------------------- |
| `TwitterAPI` | `MockTwitterAPI` → lee `fixtures/twitter/*.json` | `RealTwitterAPI` → twitterapi.io |
| `CMS`        | `MockCMS` → escribe `cms_mock.jsonl`             | `RealCMS` → CMS REST             |
| Scrapers     | parsean `fixtures/outlets/*.json`                | selectores CSS reales            |

Los `fixtures/` son los **datos canned de entrada** que sirven los mocks (no son las tools).

### ⛔ Pendiente / placeholder real (Fase F + definiciones del cliente)

- `RealTwitterAPI` / `RealCMS` → hoy lanzan `NotImplementedError`. Implementar contra las APIs reales
  cuando haya keys.
- Selectores reales de los 5 scrapers; `config/sources.yaml` (50 cuentas X + 5 medios, hoy placeholders).
- Contenido real de los 3 prompts editables (`hermes/prompts/{editorial,filtering,twitter}.md`) — hoy
  borradores con `TODO`; **la línea editorial la define el cliente**.
- Conexión real de Telegram (bot token + grupo/topic).

### Mapa del repo

- `patriota_tools/` — servidor MCP: `server.py` (tools), `storage/db.py` (SQLite), `adapters/`
  (twitterapi, cms), `scrapers/`, `config.py`.
- `hermes/` — `AGENTS.md` (persona), `config.yaml`, `skills/` (editorial-flow, twitter-flow,
  weekly-summary, skill-builder), `prompts/`, `cron/seed-jobs.md`.
- `fixtures/` — datos mock. `config/sources.yaml` — fuentes. `tests/` — unidad + integración.
- `docker-compose.yml` — servicios `hermes` (chat básico, imagen stock), `hermes-mcp` (perfil `b2`,
  con las tools MCP, todo mockeado, **no requiere keys**), `tools` (Track A, pipeline determinístico).

### Próximo paso

Sumar keys de servicios externos e implementar `RealTwitterAPI`/`RealCMS`/scrapers (Fase F). Las
skills + tools MCP (Track B2) ya andan sobre mocks **sin keys**, así que se puede seguir
desarrollando el flujo del agente antes de que lleguen las credenciales.
