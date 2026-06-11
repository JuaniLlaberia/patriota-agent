## Comandos principales

### Primera vez (setup completo)

```bash
# 1. Exportar UID/GID para que los archivos del volumen sean tuyos
export HERMES_UID=$(id -u) HERMES_GID=$(id -g)

# 2. Construir la imagen con patriota-tools instalado
docker compose build hermes-gateway

# 3. Levantar el gateway — registra MCP, crea los cron jobs y arranca solo
docker compose up -d hermes-gateway

# 4. Ver logs en vivo
docker compose logs -f hermes-gateway
```

> El script `start-gateway.sh` corre en cada inicio del contenedor: registra el
> servidor MCP con las variables de entorno actuales, y crea/actualiza los 3 cron
> jobs automáticamente antes de lanzar `hermes gateway`. No se necesitan pasos manuales.

### Chat interactivo (dev / debug)

```bash
docker compose run --rm --profile b2 hermes-mcp chat
```

### Modelo

```bash
docker compose run --rm hermes model
```

---

## Variables de entorno (`hermes/.env`)

```
ANTHROPIC_API_KEY=          # opcional — si usás modelos Anthropic directamente
OPENROUTER_API_KEY=         # requerido para modelos OpenAI (gpt-4o-mini, gpt-4.1-mini, etc.)
OPENAI_API_KEY=             # opcional — solo para TTS/STT, no para inferencia LLM
HERMES_MODEL=               # override del modelo (default: openai/gpt-4o-mini)
TELEGRAM_BOT_TOKEN=         # token de @BotFather
TELEGRAM_HOME_CHANNEL=      # chat_id del grupo editor (int negativo)
TELEGRAM_ALLOWED_USERS=     # tu user id de Telegram (ej. 123456789)
TWITTERAPI_IO_KEY=          # twitterapi.io — monitoring de X/Twitter
CMS_BASE_URL=               # endpoint del CMS REST
CMS_API_TOKEN=              # token del CMS
```

---

## Estado del proyecto

**Qué es.** Agente editorial autónomo de _El Patriota_ (diario digital argentino) construido
**sobre [Hermes Agent](https://hermes-agent.nousresearch.com/)** (Nous Research, MIT). Hermes
aporta el loop, memoria, skills, cron y Telegram; nosotros aportamos las _capacidades de
dominio_ como un servidor MCP (`patriota-tools`) + skills + cron.
LLM = OpenAI vía OpenRouter (default: `gpt-4o-mini`; override con `HERMES_MODEL`). Opera en español rioplatense, con `/aprobar` humano antes de publicar.

### ✅ Funciona hoy

- **Gateway de Telegram bidireccional** — `hermes-gateway` corre `hermes gateway` como
  daemon con `restart: unless-stopped`. Los editores interactúan directamente en el grupo.
  Bot: `@AgentePatriotaBot`. Autorización por `TELEGRAM_ALLOWED_USERS`.

- **Servidor MCP `patriota-tools`** — ~25 tools (`mcp_patriota_*`) sobre SQLite. Cubre
  ingesta + dedup, clustering (mín 2 fuentes), pipeline de notas
  (`title_proposed → summary_approved → published`), pipeline de tweets, versionado de
  prompts y trazabilidad (fuentes + timestamp + versión de prompt).

- **Scrapers RSS reales (7 medios)** — `RSSFeedScraper` con `feedparser`. Feeds verificados:

  | id         | Medio              | Feed RSS                                                    |
  |------------|--------------------|-------------------------------------------------------------|
  | `infobae`  | Infobae            | `https://www.infobae.com/arc/outboundfeeds/rss/`            |
  | `lanacion` | La Nación          | `https://www.lanacion.com.ar/arc/outboundfeeds/rss/`        |
  | `tn`       | TN (Todo Noticias) | `https://tn.com.ar/feed/`                                   |
  | `clarin`   | Clarín             | `https://www.clarin.com/rss/`                               |
  | `cronista` | El Cronista        | `https://www.cronista.com/feed/`                            |
  | `ambito`   | Ámbito Financiero  | `https://www.ambito.com/rss/pages/ultimas-noticias.xml`     |
  | `iproup`   | iProup             | `https://www.iproup.com/feed/`                              |

- **Monitoreo de Twitter/X** — `RealTwitterAPI` contra `api.twitterapi.io` (auth:
  `X-API-Key`). Implementado: `monitor_accounts`, `get_trends` (WOEID 455827),
  `search`. Requiere `TWITTERAPI_IO_KEY` en `hermes/.env`; sin la key cae al mock
  automáticamente.

- **Chat + identidad de El Patriota** — persona en `hermes/AGENTS.md`, auto-inyectada
  por Hermes desde el workdir `/opt/data`.

- **111 cuentas de X/Twitter monitoreadas** — `config/sources.yaml` con handles reales
  organizados por categoría (medios, periodistas, políticos, think tanks, embajadas, etc.).

- **Cron jobs auto-seeded** — `hermes/scripts/start-gateway.sh` crea/actualiza los 3 jobs
  en cada arranque del contenedor (monitoreo 45min, twitter diario 12UTC, resumen semanal lunes 13UTC).

- **Tool-use forzado** — `agent.tool_use_enforcement: true` en config; evita que modelos GPT
  narren tool calls en vez de ejecutarlos.

### 🟡 Mockeado / pendiente de credencial

| Adapter      | Estado actual                                    | Para activar               |
|--------------|--------------------------------------------------|----------------------------|
| `TwitterAPI` | Mock si falta `TWITTERAPI_IO_KEY`                | Agregar key a `hermes/.env` |
| `CMS`        | `MockCMS` → escribe `cms_mock.jsonl`             | Implementar `RealCMS` con endpoint + token del cliente |
| Scrapers     | `USE_MOCKS=false` en `hermes-gateway` (real RSS) | Ya activo                  |

### ⛔ Pendiente

- **`RealCMS`** — `publish_draft` lanza `NotImplementedError`. Implementar contra el
  CMS REST del cliente cuando lleguen las credenciales.
- **Publicación de tweets** — `RealTwitterAPI.publish` es `NotImplementedError` (fuera
  de scope). Requiere Twitter API v2 + OAuth 2.0 propio de El Patriota.
- **Prompts editoriales** — `hermes/prompts/{editorial,filtering,twitter}.md` tienen
  borradores con `TODO`; la línea editorial la define el cliente.

### Mapa del repo

- `patriota_tools/` — servidor MCP: `server.py` (tools), `storage/db.py` (SQLite),
  `adapters/` (twitterapi, cms), `scrapers/` (base + 7 outlets RSS), `config.py`.
- `hermes/` — `AGENTS.md` (persona), `config.yaml`, `skills/` (editorial-flow,
  twitter-flow, weekly-summary, skill-builder), `prompts/`, `cron/seed-jobs.md`.
- `fixtures/` — datos mock para los 7 medios + Twitter. `config/sources.yaml` — fuentes.
- `docker-compose.yml` — `hermes` (chat B1), `hermes-mcp` (chat B2, perfil `b2`),
  `hermes-gateway` (bot Telegram + cron, always-on), `tools` (MCP standalone).
