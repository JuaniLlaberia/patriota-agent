"""Scraper base class + normalized article schema."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel


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

    @abstractmethod
    def parse(self, html: str) -> list[NormalizedArticle]:
        """Parse a listing/article HTML page into normalized articles.

        TODO Phase F: implement per-outlet selectors with BeautifulSoup.
        """
