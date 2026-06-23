"""Two-prompt article generation pipeline for El Patriota.

Prompt 1 (temperature 0.7): generates a full article draft from source items.
Prompt 2 (temperature 0.3): re-checks and humanises the draft.
Both use GPT-4o-mini via OpenRouter.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import openai

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "openai/gpt-4o-mini"


class ArticleGenerator:
    """Generate article drafts via the two-prompt pipeline."""

    def __init__(self, openrouter_api_key: str, model: str = _DEFAULT_MODEL) -> None:
        self._client = openai.OpenAI(
            api_key=openrouter_api_key,
            base_url="https://openrouter.ai/api/v1",
        )
        self._model = model

    # ── Source context builder ───────────────────────────────────────────────

    def build_sources_context(self, items: list[dict[str, Any]]) -> str:
        """Format source items ordered by engagement descending."""

        def _engagement(item: dict) -> int:
            try:
                raw = json.loads(item.get("raw") or "{}")
            except (json.JSONDecodeError, TypeError):
                raw = {}
            return int(raw.get("likeCount") or raw.get("likes") or 0)

        lines = []
        for i, item in enumerate(sorted(items, key=_engagement, reverse=True), 1):
            try:
                raw = json.loads(item.get("raw") or "{}")
            except (json.JSONDecodeError, TypeError):
                raw = {}
            score = int(raw.get("likeCount") or raw.get("likes") or 0)
            eng_str = f" ({score:,} likes)" if score else ""
            source = item.get("source") or "fuente desconocida"
            date = item.get("published_at") or item.get("ingested_at") or ""
            body_preview = (item.get("body") or "")[:400]
            lines.append(
                f"FUENTE {i} — {source}{eng_str} — {date}\n"
                f"{item.get('title') or ''}\n"
                f"{body_preview}\n"
                f"URL: {item.get('url') or ''}"
            )
        return "\n\n".join(lines)

    # ── Two-prompt pipeline ──────────────────────────────────────────────────

    def _call(
        self,
        system: str,
        user: str,
        temperature: float,
        max_tokens: int = 2000,
    ) -> str:
        for attempt in range(2):
            try:
                resp = self._client.chat.completions.create(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=30,
                )
                return resp.choices[0].message.content or ""
            except Exception as exc:
                if attempt == 0:
                    logger.warning("LLM generation call failed (retrying): %s", exc)
                else:
                    raise
        return ""

    def generate(
        self,
        items: list[dict[str, Any]],
        editorial_prompt: str,
        recheck_prompt: str,
    ) -> dict[str, Any]:
        """Run the two-prompt pipeline. Returns {titulo, bajada, volanta, texto_html}."""
        sources_block = self.build_sources_context(items)
        draft = self._call(
            system="Sos el redactor de El Patriota. Escribís en español rioplatense.",
            user=editorial_prompt.rstrip() + f"\n\nFUENTES:\n\n{sources_block}",
            temperature=0.7,
        )
        final_text = self._call(
            system="Sos el editor de El Patriota. Rechequear y humanizar el siguiente borrador.",
            user=recheck_prompt.rstrip() + f"\n\nBORRADOR:\n\n{draft}",
            temperature=0.3,
        )
        return self.parse_output(final_text)

    # ── Output parser ────────────────────────────────────────────────────────

    def parse_output(self, text: str) -> dict[str, Any]:
        """Extract titulo, bajada, volanta, texto_html from generated text."""
        _LABEL_RE = re.compile(
            r"^\*{0,2}(título|title|bajada|volanta|cuerpo|body)\*{0,2}\s*:\s*",
            re.IGNORECASE,
        )

        def _strip_label(line: str) -> str:
            return _LABEL_RE.sub("", line).strip()

        def _is_cuerpo_header(line: str) -> bool:
            return bool(re.match(r"^\*{0,2}cuerpo\*{0,2}\s*:?\s*$", line, re.IGNORECASE))

        lines = text.strip().splitlines()
        non_empty = [l for l in lines if l.strip()]

        titulo = _strip_label(non_empty[0]) if non_empty else ""

        volanta = ""
        bajada = ""
        body_lines: list[str] = []

        for i, line in enumerate(non_empty[1:], 1):
            stripped = line.strip()
            clean = _strip_label(stripped)
            if re.match(r"^\*{0,2}volanta\*{0,2}\s*:", stripped, re.IGNORECASE):
                volanta = clean
            elif _is_cuerpo_header(stripped):
                # "Cuerpo:" is a section header with no inline content — skip it
                body_lines = [_strip_label(l) for l in non_empty[i + 1:] if l.strip()]
                break
            elif not bajada and len(clean) > 60:
                bajada = clean
                body_lines = [_strip_label(l) for l in non_empty[i + 1:] if l.strip()]
                break

        # Remove any stray "Cuerpo:" header that ended up inside body_lines
        body_lines = [l for l in body_lines if not _is_cuerpo_header(l)]

        return {
            "titulo": titulo,
            "bajada": bajada,
            "volanta": volanta,
            "texto_html": _to_html(body_lines),
        }


def _to_html(lines: list[str]) -> str:
    parts = []
    for line in lines:
        s = line.strip()
        if not s:
            continue
        if len(s) < 80 and s[-1] not in ".,:;!?)'\"":
            parts.append(f"<h2>{s}</h2>")
        else:
            parts.append(f"<p>{s}</p>")
    return "\n".join(parts)
