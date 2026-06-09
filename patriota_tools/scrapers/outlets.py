"""The 7 outlet scrapers + the registry and the mock-aware scrape entrypoint."""

from __future__ import annotations

import json
from typing import Any

from ..config import Settings
from .base import NormalizedArticle, RSSFeedScraper, Scraper


class Infobae(RSSFeedScraper):
    outlet_id = "infobae"
    base_url = "https://www.infobae.com"
    feed_url = "https://www.infobae.com/arc/outboundfeeds/rss/"


class LaNacion(RSSFeedScraper):
    outlet_id = "lanacion"
    base_url = "https://www.lanacion.com.ar"
    feed_url = "https://www.lanacion.com.ar/arc/outboundfeeds/rss/"


class TN(RSSFeedScraper):
    outlet_id = "tn"
    base_url = "https://tn.com.ar"
    feed_url = "https://tn.com.ar/feed/"


class Clarin(RSSFeedScraper):
    outlet_id = "clarin"
    base_url = "https://www.clarin.com"
    feed_url = "https://www.clarin.com/rss/"


class ElCronista(RSSFeedScraper):
    outlet_id = "cronista"
    base_url = "https://www.cronista.com"
    feed_url = "https://www.cronista.com/feed/"


class Ambito(RSSFeedScraper):
    outlet_id = "ambito"
    base_url = "https://www.ambito.com"
    feed_url = "https://www.ambito.com/rss/pages/ultimas-noticias.xml"


class iProup(RSSFeedScraper):
    outlet_id = "iproup"
    base_url = "https://www.iproup.com"
    feed_url = "https://www.iproup.com/feed/"


OUTLETS: dict[str, type[Scraper]] = {
    s.outlet_id: s
    for s in (Infobae, LaNacion, TN, Clarin, ElCronista, Ambito, iProup)
}


def _load_fixture_articles(settings: Settings, outlet_id: str) -> list[dict[str, Any]]:
    path = settings.fixtures / "outlets" / f"{outlet_id}.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [NormalizedArticle(**a).to_source_item() for a in data]


def scrape_outlet(settings: Settings, outlet_id: str) -> list[dict[str, Any]]:
    """Return normalized source_items for one outlet.

    Mock mode: read fixtures/outlets/<id>.json.
    Real mode: fetch the outlet's RSS feed.
    """
    if outlet_id not in OUTLETS:
        raise ValueError(f"Unknown outlet: {outlet_id}")
    if settings.use_mocks:
        return _load_fixture_articles(settings, outlet_id)
    return OUTLETS[outlet_id]().scrape()
