"""CMS publishing adapter.

Mock appends draft payloads to a JSONL log so the full flow is testable; the real
client (Phase F) does an authenticated HTTP POST to El Patriota's CMS REST API
(spec from Fase 0 — endpoint, auth, fields, draft state).
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import Settings


class CMSClient(ABC):
    @abstractmethod
    def publish_draft(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create a CMS entry in 'borrador' (draft) state. Returns {cms_id, url}."""


class MockCMS(CMSClient):
    """Appends drafts to {db_dir}/cms_mock.jsonl and returns a fake id."""

    def __init__(self, log_path: Path):
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
    """El Patriota CMS REST client. TODO Phase F: implement the POST.

    Expected payload fields (confirm against the CMS API spec from Fase 0):
      titulo, cuerpo, bajada, tags[], estado='borrador',
      trazabilidad{fuentes[], timestamp, prompt_version}
    """

    def __init__(self, base_url: str, token: str):
        self.base_url = base_url
        self.token = token

    def publish_draft(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError("RealCMS.publish_draft not implemented (Phase F).")


def get_cms(settings: Settings) -> CMSClient:
    if settings.use_mocks or not settings.cms_base_url:
        log_path = Path(settings.db_path).expanduser().parent / "cms_mock.jsonl"
        return MockCMS(log_path)
    return RealCMS(settings.cms_base_url, settings.cms_api_token or "")
