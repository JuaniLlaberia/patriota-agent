"""Shared text cleanup for scraped/ingested content before it reaches an LLM prompt.

RSS bodies often carry outlet boilerplate (subscribe CTAs, share prompts, newsletter
pitches, "read more" links) alongside the actual article text. Stripping that noise
before it's sent to the model shrinks prompt size, which helps avoid rate limits and
keeps the model focused on the actual story.
"""

from __future__ import annotations

import re

# Block-level tag closes become line breaks so boilerplate can be matched per-line
# before the remaining tags are stripped.
_BLOCK_CLOSE_RE = re.compile(r"</(p|div|li|h[1-6])>|<br\s*/?>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_URL_RE = re.compile(r"https?://\S+")
_WS_RE = re.compile(r"\s+")

# Common Argentine news-site boilerplate lines — matched whole-line, case-insensitive.
_BOILERPLATE_RE = re.compile(
    r"^("
    r"suscrib\S*.*|"
    r"segu[ií] leyendo.*|"
    r"segu[íi] leyendo.*|"
    r"continu[ae]r? leyendo.*|"
    r"compart[ií] (esta|este) (nota|noticia|art[íi]culo).*|"
    r"compartir en (facebook|twitter|whatsapp|x)\b.*|"
    r"publicidad\b.*|"
    r"newsletter\b.*|"
    r"tambi[ée]n te puede interesar:?.*|"
    r"te puede interesar:?.*|"
    r"noticias? relacionadas?:?.*|"
    r"le[ée] tambi[ée]n:?.*|"
    r"mir[áa] tambi[ée]n:?.*|"
    r"cliquea[áa]? aqu[íi].*|"
    r"clic(k)? aqu[íi].*|"
    r"fuente:\s*\S+"
    r")$",
    re.IGNORECASE,
)


def clean_article_text(text: str | None) -> str:
    """Strip HTML tags, outlet boilerplate/CTAs, and stray URLs from body text."""
    if not text:
        return ""
    text = _BLOCK_CLOSE_RE.sub("\n", text)
    text = _TAG_RE.sub(" ", text)
    text = _URL_RE.sub("", text)

    lines = [ln.strip() for ln in re.split(r"[\r\n]+", text) if ln.strip()]
    kept = [ln for ln in lines if not _BOILERPLATE_RE.match(ln)]
    cleaned = " ".join(kept) if kept else " ".join(lines)
    return _WS_RE.sub(" ", cleaned).strip()
