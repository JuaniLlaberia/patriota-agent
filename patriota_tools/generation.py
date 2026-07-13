"""Two-prompt article generation pipeline for El Patriota.

Prompt 1 (temperature 0.7): generates a full article draft from source items.
Prompt 2 (temperature 0.3): re-checks and humanises the draft.
Both call GPT-4o-mini directly against the OpenAI API (not via OpenRouter) — the
direct API has a dedicated per-org rate limit pool instead of OpenRouter's shared one,
which is what article generation was hitting.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

import openai

from .textclean import clean_article_text

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "gpt-4o-mini"


class ArticleGenerator:
    """Generate article drafts via the two-prompt pipeline."""

    def __init__(self, openai_api_key: str, model: str = _DEFAULT_MODEL) -> None:
        self._client = openai.OpenAI(api_key=openai_api_key)
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
            body_preview = clean_article_text(item.get("body"))[:1800]
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
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        delay = 5.0
        for attempt in range(4):
            try:
                resp = self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=30,
                )
                return resp.choices[0].message.content or ""
            except openai.RateLimitError as exc:
                if attempt == 3:
                    raise
                logger.warning(
                    "Rate limited (attempt %d/4); backing off %.0fs: %s", attempt + 1, delay, exc
                )
                time.sleep(delay)
                delay *= 3
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
        """Run the two-prompt pipeline. Returns {titulo, bajada, volanta, body_text}."""
        sources_block = self.build_sources_context(items)
        draft = self._call(
            system="Sos el redactor de El Patriota. Escribís en español rioplatense.",
            user=editorial_prompt.rstrip() + f"\n\nFUENTES:\n\n{sources_block}",
            temperature=0.7,
            max_tokens=4000,
        )
        final_text = self._call(
            system="Sos el editor de El Patriota. Rechequear y humanizar el siguiente borrador.",
            user=recheck_prompt.rstrip() + f"\n\nBORRADOR:\n\n{draft}",
            temperature=0.3,
            max_tokens=4000,
        )
        return self.parse_output(final_text)

    # ── Output parser ────────────────────────────────────────────────────────

    def parse_output(self, text: str) -> dict[str, Any]:
        """Extract titulo, bajada, volanta, body_text from generated text.

        Follows the structure the editorial prompt mandates — line 1: título,
        line 2: bajada, resto: cuerpo — instead of guessing by line length (which
        dropped short bajadas and swallowed the first body paragraph). Optional
        'Volanta:' / 'Cuerpo:' label lines are tolerated but not required.
        """
        _LABEL_RE = re.compile(
            r"^\*{0,2}(título|title|bajada|volanta|cuerpo|body)\*{0,2}\s*:\s*",
            re.IGNORECASE,
        )

        def _strip_label(line: str) -> str:
            return _LABEL_RE.sub("", line).strip()

        def _is_cuerpo_header(line: str) -> bool:
            return bool(re.match(r"^\*{0,2}cuerpo\*{0,2}\s*:?\s*$", line, re.IGNORECASE))

        non_empty = [l.strip() for l in text.strip().splitlines() if l.strip()]
        if not non_empty:
            return {"titulo": "", "bajada": "", "volanta": "", "body_text": ""}

        titulo = _strip_label(non_empty[0])
        rest = non_empty[1:]

        # Optional explicit volanta line (the prompt omits it, but tolerate it).
        volanta = ""
        if rest and re.match(r"^\*{0,2}volanta\*{0,2}\s*:", rest[0], re.IGNORECASE):
            volanta = _strip_label(rest[0])
            rest = rest[1:]

        # Skip any stray 'Cuerpo:' header sitting where the bajada should be.
        while rest and _is_cuerpo_header(rest[0]):
            rest = rest[1:]

        # Line 2 is the bajada; everything after it is the body.
        bajada = _strip_label(rest[0]) if rest else ""
        body_lines = [_strip_label(l) for l in rest[1:] if not _is_cuerpo_header(l)]

        return {
            "titulo": _strip_markdown(titulo),
            "bajada": _strip_markdown(bajada),
            "volanta": _strip_markdown(volanta),
            "body_text": _to_body_text(body_lines),
        }


def _strip_markdown(text: str) -> str:
    """Remove common markdown formatting, leaving plain text."""
    # headings: ## Heading → Heading
    text = re.sub(r"^#{1,6}\s+", "", text)
    # bold+italic: ***text*** or ___text___
    text = re.sub(r"\*{3}(.+?)\*{3}", r"\1", text)
    text = re.sub(r"_{3}(.+?)_{3}", r"\1", text)
    # bold: **text** or __text__
    text = re.sub(r"\*{2}(.+?)\*{2}", r"\1", text)
    text = re.sub(r"_{2}(.+?)_{2}", r"\1", text)
    # italic: *text* or _text_
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"_(.+?)_", r"\1", text)
    # inline code: `text`
    text = re.sub(r"`(.+?)`", r"\1", text)
    # links: [text](url) → text
    text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)
    # blockquote prefix
    text = re.sub(r"^>\s*", "", text)
    return text.strip()


def _to_body_text(lines: list[str]) -> str:
    """Join paragraphs as plain text separated by a blank line.

    The CMS body field preserves literal newlines (markdown-ish / nl2br textarea),
    so a blank line between paragraphs is what renders as a paragraph break there —
    inline <p> tags were being collapsed. Kept plain so the DB stores plain text too.
    """
    parts = [s for line in lines if (s := _strip_markdown(line.strip()))]
    return "\n\n".join(parts)
