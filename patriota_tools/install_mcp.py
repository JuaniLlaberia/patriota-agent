"""Register the patriota MCP server in Hermes' config.yaml.

Workaround for a Hermes bug: the `hermes mcp add` CLI crashes when `typer` is
missing from Hermes' own venv. This injector writes the `mcp_servers` entry
directly into the config file.

Run once after installing patriota-tools, and again whenever env vars change:
    patriota-install-mcp
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml


def main() -> None:
    home = os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))
    cfg_path = Path(os.environ.get("HERMES_CONFIG", f"{home}/config.yaml"))

    data = {}
    if cfg_path.exists():
        data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}

    servers = data.setdefault("mcp_servers", {})
    mcp_env = {
        "USE_MOCKS": os.environ.get("USE_MOCKS", "true"),
        "PATRIOTA_DB_PATH": os.environ.get("PATRIOTA_DB_PATH", f"{home}/patriota.db"),
        "PATRIOTA_PROMPTS_DIR": os.environ.get(
            "PATRIOTA_PROMPTS_DIR", "/opt/patriota/prompts"
        ),
    }
    for optional in (
        "TWITTERAPI_IO_KEY",
        "OPENAI_API_KEY",
        "OPENROUTER_API_KEY",
        "CMS_API_URL_BASE",
        "CMS_CLIENT_ID",
        "CMS_CLIENT_SECRET",
        "CMS_USERNAME",
        "CMS_PASSWORD",
    ):
        val = os.environ.get(optional)
        if val:
            mcp_env[optional] = val

    servers["patriota"] = {
        "command": os.environ.get(
            "PATRIOTA_MCP_COMMAND", "/opt/patriota/venv/bin/patriota-tools"
        ),
        "env": mcp_env,
        "enabled": True,
        "timeout": int(os.environ.get("PATRIOTA_MCP_TIMEOUT", "600")),
        "connect_timeout": int(os.environ.get("PATRIOTA_MCP_CONNECT_TIMEOUT", "60")),
    }

    model_override = os.environ.get("HERMES_MODEL")
    if model_override:
        data["model"] = model_override
    else:
        data.setdefault("model", "deepseek/deepseek-v4-flash")
    data.setdefault("agent", {})["tool_use_enforcement"] = True
    data.setdefault("generation", {}).setdefault("temperature", 0.1)

    cfg_path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    print(f"✓ Registrado mcp_servers.patriota en {cfg_path} (enabled: true)")
    print("  Reiniciá/relanzá el chat para que Hermes levante el servidor MCP.")


if __name__ == "__main__":
    main()
