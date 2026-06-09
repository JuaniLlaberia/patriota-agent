"""Scraper base classes + normalized article schema."""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class NormalizedArticle(BaseModel):
    """Common shape every outlet scraper must produce."""

    outlet: str
    title: str
    body: str = ""
    url: str
    author: str | None = None
    section: str | None = None
    published_at: str | None = None

    def to_source_item(self) -> dict[str, Any]:
        return {
            "kind": "article",
            "source": self.outlet,
            "title": self.title,
            "body": self.body,
            "url": self.url,
            "author": self.author,
            "section": self.section,
            "published_at": self.published_at,
            "dedupe_key": f"article:{self.url}",
            "raw": self.model_dump(),
        }


class Scraper(ABC):
    """One per outlet. `outlet_id` matches config/sources.yaml + the fixture filename."""

    outlet_id: str = ""
    base_url: str = ""

    def scrape(self) -> list[dict[str, Any]]:
        """Fetch content and return normalized source_items."""
        raise NotImplementedError(f"{self.outlet_id}: scrape() not implemented.")

    @abstractmethod
    def parse(self, html: str) -> list[NormalizedArticle]:
        """Parse raw HTML into articles (for HTML-based scrapers)."""


class RSSFeedScraper(Scraper):
    """Fetch an RSS/Atom feed with feedparser and normalize entries."""

    feed_url: str = ""

    def scrape(self) -> list[dict[str, Any]]:
        import feedparser  # lazy import so mock mode never needs it

        try:
            feed = feedparser.parse(
                self.feed_url,
                agent="patriota-tools/0.1 (news monitor)",
            )
        except Exception as exc:
            logger.warning("RSS fetch failed for %s: %s", self.outlet_id, exc)
            return []

        articles = []
        for entry in feed.entries:
            article = self._entry_to_article(entry)
            if article:
                articles.append(article.to_source_item())
        return articles

    def _entry_to_article(self, entry: Any) -> NormalizedArticle | None:
        url = entry.get("link", "").strip()
        title = entry.get("title", "").strip()
        if not url or not title:
            return None

        # Body: prefer full content > summary
        body = ""
        content = entry.get("content")
        if content:
            body = content[0].get("value", "")
        elif entry.get("summary"):
            body = entry.summary or ""
        body = re.sub(r"<[^>]+>", " ", body)
        body = re.sub(r"\s+", " ", body).strip()

        # Date
        t = entry.get("published_parsed") or entry.get("updated_parsed")
        published_at: str | None = None
        if t:
            published_at = datetime(*t[:6], tzinfo=timezone.utc).isoformat()

        # Section from first tag
        section: str | None = None
        tags = entry.get("tags", [])
        if tags:
            section = tags[0].get("term") or tags[0].get("label")

        return NormalizedArticle(
            outlet=self.outlet_id,
            title=title,
            body=body,
            url=url,
            author=entry.get("author"),
            section=section,
            published_at=published_at,
        )

    def parse(self, html: str) -> list[NormalizedArticle]:
        raise NotImplementedError(f"{self.outlet_id}: RSS scraper — use scrape(), not parse().")
