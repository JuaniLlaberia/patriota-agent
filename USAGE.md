## Despliegue en VPS (producción)

### Requisitos

- Ubuntu 22.04+ / Debian 12+ con acceso root
- Python 3.11+
- curl (para el instalador de Hermes)

### Primera vez

```bash
# 1. Clonar el repo
git clone <repo-url> /opt/patriota-agent
cd /opt/patriota-agent

# 2. Correr el instalador (como root)
sudo bash deploy/install.sh

# 3. Completar las credenciales
sudo nano /etc/patriota/env

# 4. Arrancar el servicio
sudo systemctl start patriota-gateway

# 5. Ver logs en vivo
sudo journalctl -u patriota-gateway -f
```

El instalador:
- Crea el usuario de sistema `patriota`
- Instala el CLI de Hermes para ese usuario
- Instala `patriota-tools` en un venv en `/opt/patriota/venv`
- Copia config, persona (`AGENTS.md`), skills y prompts a `~/.hermes/`
- Escribe la plantilla de secretos en `/etc/patriota/env`
- Instala y habilita el servicio systemd `patriota-gateway`

El script `start-gateway.sh` (corrido por systemd al iniciar el servicio):
1. Registra/actualiza la config del servidor MCP en `~/.hermes/config.yaml`
2. Siembra los 3 cron jobs **solo la primera vez** (usa un centinela en `~/.hermes/.cron-seeded`)
3. Lanza `hermes gateway` como proceso principal

### Actualizar después de un cambio de código

```bash
cd /opt/patriota-agent
git pull
sudo bash deploy/install.sh        # reinstala herramientas y assets
sudo systemctl restart patriota-gateway
```

### Gestión del servicio

```bash
sudo systemctl status patriota-gateway
sudo systemctl stop patriota-gateway
sudo systemctl restart patriota-gateway
sudo journalctl -u patriota-gateway -f        # logs en vivo
sudo journalctl -u patriota-gateway --since "1 hour ago"
```

### Re-sembrar los cron jobs

Los cron jobs se crean una sola vez. Si cambiás las definiciones (schedules, prompts,
skills) y querés que se apliquen, borrá el centinela y reiniciá:

```bash
sudo rm /home/patriota/.hermes/.cron-seeded
sudo systemctl restart patriota-gateway
```

> Nota: esto no toca los jobs dinámicos (tweets programados) — solo los 3 jobs base.
> Para gestionar jobs individualmente: `su -l patriota -c "hermes cron list"`

### Cambiar el modelo LLM

Editá `HERMES_MODEL` en `/etc/patriota/env` y reiniciá el servicio. El valor en el
env siempre tiene precedencia. Si `HERMES_MODEL` no está seteado, se preserva el
modelo que tenga `~/.hermes/config.yaml` en ese momento.

```bash
# Ejemplo: cambiar a Claude Sonnet
echo "HERMES_MODEL=anthropic/claude-sonnet-4-6" | sudo tee -a /etc/patriota/env
sudo systemctl restart patriota-gateway
```

### Chat interactivo (debug desde el VPS)

```bash
su -l patriota -c "hermes chat"
```

---

## Variables de entorno (`/etc/patriota/env`)

| Variable | Requerida | Descripción |
|----------|-----------|-------------|
| `OPENROUTER_API_KEY` | Sí (para GPT) | Acceso a modelos OpenAI vía OpenRouter |
| `ANTHROPIC_API_KEY` | Si usás Claude | API key de Anthropic |
| `HERMES_MODEL` | No | Override de modelo (default: `openai/gpt-4o-mini`) |
| `TELEGRAM_BOT_TOKEN` | Sí | Token del bot de @BotFather |
| `TELEGRAM_HOME_CHANNEL` | Sí | chat_id del grupo editorial (int negativo) |
| `TELEGRAM_ALLOWED_USERS` | Sí | Tu user id de Telegram (ej. `123456789`) |
| `TWITTERAPI_IO_KEY` | Para Twitter real | API key de twitterapi.io |
| `CMS_BASE_URL` | Para publicar | Endpoint REST del CMS |
| `CMS_API_TOKEN` | Para publicar | Token del CMS |

Las variables de rutas (`HERMES_HOME`, `PATRIOTA_MCP_COMMAND`, etc.) las escribe
`deploy/install.sh` automáticamente — no las edites salvo que muevas la instalación.

---

## Estado del proyecto

**Qué es.** Agente editorial autónomo de _El Patriota_ (diario digital argentino) construido
**sobre [Hermes Agent](https://hermes-agent.nousresearch.com/)** (Nous Research, MIT). Hermes
aporta el loop, memoria, skills, cron y Telegram; nosotros aportamos las _capacidades de
dominio_ como un servidor MCP (`patriota-tools`) + skills + cron.
LLM = OpenAI vía OpenRouter (default: `gpt-4o-mini`; override con `HERMES_MODEL`). Opera en español rioplatense, con `/aprobar` humano antes de publicar.

### ✅ Funciona hoy

- **Gateway de Telegram bidireccional** — `patriota-gateway` corre `hermes gateway` como
  daemon con `Restart=on-failure`. Los editores interactúan directamente en el grupo.
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
  `search`. Requiere `TWITTERAPI_IO_KEY` en `/etc/patriota/env`; sin la key cae al mock
  automáticamente.

- **Chat + identidad de El Patriota** — persona en `hermes/AGENTS.md`, copiada a
  `~/.hermes/AGENTS.md` por el instalador y auto-inyectada por Hermes desde el workdir.

- **111 cuentas de X/Twitter monitoreadas** — `config/sources.yaml` con handles reales
  organizados por categoría (medios, periodistas, políticos, think tanks, embajadas, etc.).

- **Cron jobs auto-seeded en primera ejecución** — `start-gateway.sh` crea los 3 jobs
  base solo si el centinela `~/.hermes/.cron-seeded` no existe:
  monitoreo 45min, twitter diario 12UTC, resumen semanal lunes 13UTC.

- **Tool-use forzado** — `agent.tool_use_enforcement: true` en config; evita que modelos GPT
  narren tool calls en vez de ejecutarlos.

### 🟡 Mockeado / pendiente de credencial

| Adapter      | Estado actual                                    | Para activar               |
|--------------|--------------------------------------------------|----------------------------|
| `TwitterAPI` | Mock si falta `TWITTERAPI_IO_KEY`                | Agregar key a `/etc/patriota/env` |
| `CMS`        | `MockCMS` → escribe `cms_mock.jsonl`             | Implementar `RealCMS` con endpoint + token del cliente |
| Scrapers     | `USE_MOCKS=false` en env (real RSS)              | Ya activo                  |

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
- `hermes/` — `AGENTS.md` (persona), `config.yaml` (plantilla), `skills/` (editorial-flow,
  twitter-flow, weekly-summary, skill-builder), `prompts/`, `cron/seed-jobs.md`.
- `fixtures/` — datos mock para los 7 medios + Twitter. `config/sources.yaml` — fuentes.
- `deploy/` — `install.sh` (instalador VPS), `patriota-gateway.service` (systemd).
