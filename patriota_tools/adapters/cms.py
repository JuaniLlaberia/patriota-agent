"""CMS publishing adapter — El Patriota CMS REST API v1.1.

MockCMS: appends draft payloads to a JSONL log (testable without credentials).
RealCMS: OAuth password-grant flow → POST /noticias as multipart/form-data.
         Token strategy: access token (7d) cached; refresh (30d) persisted to
         ~/.hermes/memory/cms_tokens.json; falls back to full login if expired.
"""

from __future__ import annotations

import json
import os
import time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

from ..config import Settings

_HERMES_HOME = Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes")))
_TOKEN_FILE = _HERMES_HOME / "memory" / "cms_tokens.json"
_SECCIONES_FILE = _HERMES_HOME / "memory" / "cms_secciones.json"

_ACCESS_TTL = 6.5 * 24 * 3600   # renew at 6.5 days (token expires at 7)
_REFRESH_TTL = 30 * 24 * 3600   # re-login after 30 days


class CMSClient(ABC):
    @abstractmethod
    def publish_draft(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create a CMS entry in 'borrador' (draft) state. Returns {cms_id, url}."""


class MockCMS(CMSClient):
    """Appends drafts to {db_dir}/cms_mock.jsonl and returns a fake id."""

    def __init__(self, log_path: Path) -> None:
        self._log = log_path

    def publish_draft(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._log.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc)
        cms_id = f"mock-cms-{stamp.strftime('%Y%m%d%H%M%S')}"
        record = {"cms_id": cms_id, "received_at": stamp.isoformat(), "payload": payload}
        with self._log.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        return {"cms_id": cms_id, "url": f"mock://cms/borrador/{cms_id}", "status": "borrador"}


class RealCMS(CMSClient):
    """El Patriota CMS REST client — OAuth v1.1 (password grant + refresh)."""

    def __init__(
        self,
        base_url: str,
        client_id: str,
        client_secret: str,
        username: str,
        password: str,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._client_id = client_id
        self._client_secret = client_secret
        self._username = username
        self._password = password

    # ── Token persistence ────────────────────────────────────────────────────

    def _load_tokens(self) -> dict[str, Any]:
        try:
            return json.loads(_TOKEN_FILE.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_tokens(self, tokens: dict[str, Any]) -> None:
        _TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        _TOKEN_FILE.write_text(json.dumps(tokens, indent=2, ensure_ascii=False), encoding="utf-8")

    # ── Auth flows ───────────────────────────────────────────────────────────

    def _login(self) -> dict[str, Any]:
        resp = httpx.post(
            f"{self._base}/oauth/token",
            data={
                "grant_type": "password",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "username": self._username,
                "password": self._password,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("error"):
            raise RuntimeError(f"CMS login error: {data.get('mensaje')}")
        tokens = {
            "access_token": data["access_token"],
            "refresh_token": data["refresh_token"],
            "obtained_at": time.time(),
        }
        self._save_tokens(tokens)
        return tokens

    def _refresh(self, refresh_token: str) -> dict[str, Any]:
        resp = httpx.post(
            f"{self._base}/oauth/token",
            data={
                "grant_type": "refresh_token",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "refresh_token": refresh_token,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("error"):
            raise RuntimeError(f"CMS refresh error: {data.get('mensaje')}")
        tokens = {
            "access_token": data["access_token"],
            "refresh_token": data["refresh_token"],
            "obtained_at": time.time(),
        }
        self._save_tokens(tokens)
        return tokens

    def _get_valid_token(self) -> str:
        tokens = self._load_tokens()
        age = time.time() - tokens.get("obtained_at", 0)

        if tokens.get("access_token") and age < _ACCESS_TTL:
            return tokens["access_token"]

        if tokens.get("refresh_token") and age < _REFRESH_TTL:
            try:
                tokens = self._refresh(tokens["refresh_token"])
                return tokens["access_token"]
            except Exception:
                pass  # fall through to full login

        tokens = self._login()
        return tokens["access_token"]

    # ── Secciones cache ──────────────────────────────────────────────────────

    def _get_secciones(self, token: str) -> list[dict[str, Any]]:
        try:
            cached = json.loads(_SECCIONES_FILE.read_text(encoding="utf-8"))
            if time.time() - cached.get("fetched_at", 0) < 86400:
                return cached["secciones"]
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            pass

        secciones: list[dict] = []
        pagina = 1
        while True:
            resp = httpx.get(
                f"{self._base}/secciones",
                headers={"Authorization": f"Bearer {token}"},
                params={"pagina": pagina},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            batch = data.get("secciones") or []
            secciones.extend(batch)
            paginador = data.get("paginador", {})
            if pagina >= paginador.get("paginas", 1):
                break
            pagina += 1

        _SECCIONES_FILE.parent.mkdir(parents=True, exist_ok=True)
        _SECCIONES_FILE.write_text(
            json.dumps({"fetched_at": time.time(), "secciones": secciones}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return secciones

    def _map_seccion_id(self, tema: str, secciones: list[dict]) -> int | None:
        """Heuristic topic → section mapping; case-insensitive keyword match."""
        tema_lower = tema.lower()
        keywords: dict[str, list[str]] = {
            "política": ["política", "gobierno", "milei", "congreso", "senado", "diputados"],
            "economía": ["economía", "económ", "dólar", "inflación", "banco", "fmi", "retenciones"],
            "sociedad": ["sociedad", "educación", "salud", "social"],
            "deportes": ["deporte", "fútbol", "tenis"],
            "internacionales": ["internacional", "eeuu", "trump", "mundo"],
        }
        for seccion in secciones:
            nombre = seccion.get("nombre", "").lower()
            for key, kws in keywords.items():
                if key in nombre and any(kw in tema_lower for kw in kws):
                    return seccion.get("id")
        # Fallback: first seccion alphabetically by closest name match
        return secciones[0]["id"] if secciones else None

    # ── Publish ──────────────────────────────────────────────────────────────

    def publish_draft(self, payload: dict[str, Any]) -> dict[str, Any]:
        """POST /noticias as multipart/form-data. Retries once on failure."""
        token = self._get_valid_token()
        secciones = self._get_secciones(token)
        id_seccion = self._map_seccion_id(payload.get("grupo_tema", ""), secciones)

        form: dict[str, Any] = {
            "fecha": payload.get("fecha") or datetime.now(timezone(timedelta(hours=-3))).strftime("%Y-%m-%d %H:%M:%S"),
            "titulo": payload.get("titulo", ""),
            "autor": payload.get("autor", "El Patriota"),
            "visible": "0",
            "destacada": "0",
        }
        for optional in ("bajada", "texto", "volanta"):
            if payload.get(optional):
                form[optional] = payload[optional]
        if id_seccion:
            form["id_seccion"] = str(id_seccion)

        headers = {"Authorization": f"Bearer {token}"}

        for attempt in range(2):
            try:
                resp = httpx.post(
                    f"{self._base}/noticias",
                    headers=headers,
                    data=form,
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
                if data.get("error"):
                    raise RuntimeError(
                        f"CMS error: {data.get('mensaje')} — {data.get('errores', {})}"
                    )
                noticia = data.get("noticia", {})
                cms_id = str(noticia.get("id", ""))
                return {"cms_id": cms_id, "url": f"{self._base}/noticias/{cms_id}", "status": "borrador"}
            except Exception as exc:
                if attempt == 0:
                    import time as _time
                    _time.sleep(60)
                    # Re-auth in case token expired mid-session
                    token = self._get_valid_token()
                    headers = {"Authorization": f"Bearer {token}"}
                else:
                    raise RuntimeError(f"CMS publish failed after 2 attempts: {exc}") from exc

        return {}  # unreachable


def get_cms(settings: Settings) -> CMSClient:
    has_oauth = all([
        settings.cms_api_url_base,
        settings.cms_client_id,
        settings.cms_client_secret,
        settings.cms_username,
        settings.cms_password,
    ])
    if settings.use_mocks or not has_oauth:
        log_path = Path(settings.db_path).expanduser().parent / "cms_mock.jsonl"
        return MockCMS(log_path)
    return RealCMS(  # type: ignore[arg-type]
        settings.cms_api_url_base,
        settings.cms_client_id,
        settings.cms_client_secret,
        settings.cms_username,
        settings.cms_password,
    )
