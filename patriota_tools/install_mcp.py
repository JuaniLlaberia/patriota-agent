"""Register the patriota MCP server in Hermes' config.yaml.

Workaround for this Hermes image: the `hermes mcp add` CLI crashes when run as the
`hermes` user (missing `typer`), and running it as root would write a root-owned
config the supervised gateway can't read. This injector writes the `mcp_servers`
entry directly, as whatever user invokes it (run it via the wrapper so it lands as
the `hermes` user → correct ownership).

Run inside the Hermes container:
    /opt/patriota/venv/bin/patriota-install-mcp
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml


def main() -> None:
    home = os.environ.get("HERMES_HOME", "/opt/data")
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
    for optional in ("TWITTERAPI_IO_KEY", "CMS_BASE_URL", "CMS_API_TOKEN"):
        val = os.environ.get(optional)
        if val:
            mcp_env[optional] = val

    servers["patriota"] = {
        "command": os.environ.get(
            "PATRIOTA_MCP_COMMAND", "/opt/patriota/venv/bin/patriota-tools"
        ),
        "env": mcp_env,
        "enabled": True,
    }

    data["model"] = os.environ.get("HERMES_MODEL", "openai/gpt-4o-mini")
    data.setdefault("agent", {})["tool_use_enforcement"] = True
    data.setdefault("generation", {}).setdefault("temperature", 0.1)

    cfg_path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    print(f"✓ Registrado mcp_servers.patriota en {cfg_path} (enabled: true)")
    print("  Reiniciá/relanzá el chat para que Hermes levante el servidor MCP.")


if __name__ == "__main__":
    main()
