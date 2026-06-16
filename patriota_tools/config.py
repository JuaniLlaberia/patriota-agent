"""Runtime settings for patriota-tools.

All external integrations are gated behind ``use_mocks``. While true (the default
until Phase F), no real twitterapi.io / CMS / Telegram calls are made.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _resolve(target: str, env_value: str | None) -> Path:
    """Find a bundled asset dir/file (``fixtures`` / ``config/sources.yaml``).

    Tries the explicit env override first, then a list of candidate roots that
    covers dev (repo root), the tools image, and the hermes image.
    """
    if env_value:
        return Path(env_value)
    candidates = [
        Path(__file__).resolve().parents[1],  # repo root in dev / Dockerfile.tools
        Path("/app"),                          # compose mount
        Path("/opt/patriota"),                 # Dockerfile.hermes copy
        Path.cwd(),
    ]
    for root in candidates:
        candidate = root / target
        if candidate.exists():
            return candidate
    # Fall back to the repo-root guess even if missing (clear error downstream).
    return Path(__file__).resolve().parents[1] / target


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="", extra="ignore", populate_by_name=True
    )

    # Feature flag: keep mocks on until real credentials/specs exist.
    use_mocks: bool = Field(default=True, alias="USE_MOCKS")

    # Editorial state + traceability DB.
    db_path: str = Field(default="/data/patriota.db", alias="PATRIOTA_DB_PATH")

    # Trends region (Argentina/Buenos Aires per spec).
    woeid: int = Field(default=455827, alias="PATRIOTA_WOEID")

    # External services (ignored while use_mocks is true).
    twitterapi_io_key: str | None = Field(default=None, alias="TWITTERAPI_IO_KEY")

    # OpenAI — embeddings (text-embedding-3-small, direct API — OpenRouter doesn't support embeddings).
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    # OpenRouter — article generation via GPT-4o-mini.
    openrouter_api_key: str | None = Field(default=None, alias="OPENROUTER_API_KEY")

    # CMS OAuth v1.1
    cms_api_url_base: str | None = Field(default=None, alias="CMS_API_URL_BASE")
    cms_client_id: str | None = Field(default=None, alias="CMS_CLIENT_ID")
    cms_client_secret: str | None = Field(default=None, alias="CMS_CLIENT_SECRET")
    cms_username: str | None = Field(default=None, alias="CMS_USERNAME")
    cms_password: str | None = Field(default=None, alias="CMS_PASSWORD")

    # Asset locations (auto-resolved; override via env if needed).
    fixtures_dir: str | None = Field(default=None, alias="PATRIOTA_FIXTURES_DIR")
    sources_path: str | None = Field(default=None, alias="PATRIOTA_SOURCES_PATH")
    # Editable editorial prompts (seeded into the DB on first run). Default points at
    # the mounted Hermes home; falls back to the repo's hermes/prompts in dev.
    prompts_dir: str | None = Field(default=None, alias="PATRIOTA_PROMPTS_DIR")

    @property
    def fixtures(self) -> Path:
        return _resolve("fixtures", self.fixtures_dir)

    @property
    def sources(self) -> Path:
        if self.sources_path:
            return Path(self.sources_path)
        return _resolve("config", None) / "sources.yaml"

    @property
    def prompts(self) -> Path:
        if self.prompts_dir:
            return Path(self.prompts_dir)
        mounted = Path("/root/.hermes/prompts")
        try:
            if mounted.exists():
                return mounted
        except OSError:
            pass  # e.g. non-root user can't traverse /root in the tools image
        return _resolve("hermes", None) / "prompts"


def load_settings() -> Settings:
    return Settings()
