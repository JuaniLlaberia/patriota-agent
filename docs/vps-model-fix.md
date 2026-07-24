# Corregir el modelo del gateway en el VPS

## Por qué pasa esto

Los logs muestran `model=openai/gpt-4o-mini` aunque el repo usa `deepseek/deepseek-v4-flash`
porque `HERMES_MODEL` en `/etc/patriota/env` **siempre tiene precedencia** sobre el valor
de `hermes/config.yaml` — lo aplica `patriota-install-mcp`, que corre en cada arranque del
gateway (`start-gateway.sh`). Si esa variable quedó seteada a gpt-4o-mini de una config
anterior, cada `git pull` + reinstall la vuelve a escribir en `~/.hermes/config.yaml`, sin
importar cuántas veces cambies el modelo en el código.

Esto es también la causa de los errores 429 (`rate_limit_exceeded` en gpt-4o-mini): mientras
el gateway siga llamando a gpt-4o-mini, sigue consumiendo el pool de tokens/min de tu
organización de OpenAI.

## Pasos

Conectate al VPS por SSH y ejecutá:

### 1. Verificar el valor actual

```bash
grep HERMES_MODEL /etc/patriota/env
```

Si ves algo como `HERMES_MODEL=openai/gpt-4o-mini`, ese es el problema.

### 2. Corregir la variable

Editá el archivo:

```bash
sudo nano /etc/patriota/env
```

Tenés dos opciones:

**Opción A (recomendada) — comentar la línea**, para que el gateway use el default del
repo (`deepseek/deepseek-v4-flash`, definido en `hermes/config.yaml` y en
`patriota_tools/install_mcp.py`):

```
# HERMES_MODEL=openai/gpt-4o-mini
```

**Opción B — setearla explícitamente** al modelo correcto:

```
HERMES_MODEL=deepseek/deepseek-v4-flash
```

Guardá y cerrá (`Ctrl+O`, `Enter`, `Ctrl+X` en nano).

### 3. Reiniciar el servicio

```bash
sudo systemctl restart patriota-gateway
```

Esto vuelve a correr `start-gateway.sh`, que llama a `patriota-install-mcp` y reescribe
`~/.hermes/config.yaml` con el modelo correcto.

### 4. Verificar que tomó el cambio

```bash
# Confirmá el modelo en el config generado:
grep '^model:' /home/patriota/.hermes/config.yaml
# → debería decir: model: deepseek/deepseek-v4-flash

# Mirá los logs en vivo y confirmá que ya no aparece gpt-4o-mini:
sudo journalctl -u patriota-gateway -f
```

Buscá líneas `agent.conversation_loop` — deberían mostrar `model=deepseek/deepseek-v4-flash`
en vez de `model=openai/gpt-4o-mini`. Con esto también deberían desaparecer los 429 de
`rate_limit_exceeded`, porque nada seguirá golpeando el pool de gpt-4o-mini de tu
organización de OpenAI.

## Nota sobre futuros cambios de modelo

Esta variable siempre gana. La próxima vez que quieras cambiar el modelo del gateway,
alcanza con:

```bash
sudo nano /etc/patriota/env      # editar HERMES_MODEL
sudo systemctl restart patriota-gateway
```

No hace falta tocar `hermes/config.yaml` en el repo salvo que quieras cambiar el **default**
para instalaciones nuevas.
