"""The 5 outlet scrapers + the registry and the mock-aware scrape entrypoint.

Outlet ids are placeholders (medio_1..medio_5) matching config/sources.yaml; rename
to the real outlets and fill in selectors during Fase 1 / Phase F.
"""

from __future__ import annotations

import json
from typing import Any

from ..config import Settings
from .base import NormalizedArticle, Scraper


class _OutletScraper(Scraper):
    """Shared skeleton. Real selectors are per-outlet — override `parse`."""

    def parse(self, html: str) -> list[NormalizedArticle]:
        # TODO Phase F: parse `html` with BeautifulSoup using this outlet's
        # selectors (article cards, title, body, author, section, date).
        raise NotImplementedError(
            f"{self.outlet_id}: real HTML parsing pending (Phase F)."
        )


class Medio1(_OutletScraper):
    outlet_id = "medio_1"
    base_url = "https://example-medio-1.com.ar"


class Medio2(_OutletScraper):
    outlet_id = "medio_2"
    base_url = "https://example-medio-2.com.ar"


class Medio3(_OutletScraper):
    outlet_id = "medio_3"
    base_url = "https://example-medio-3.com.ar"


class Medio4(_OutletScraper):
    outlet_id = "medio_4"
    base_url = "https://example-medio-4.com.ar"


class Medio5(_OutletScraper):
    outlet_id = "medio_5"
    base_url = "https://example-medio-5.com.ar"


OUTLETS: dict[str, type[Scraper]] = {
    s.outlet_id: s for s in (Medio1, Medio2, Medio3, Medio4, Medio5)
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
    Real mode (Phase F): fetch base_url and run the outlet's `parse`.
    """
    if outlet_id not in OUTLETS:
        raise ValueError(f"Unknown outlet: {outlet_id}")
    if settings.use_mocks:
        return _load_fixture_articles(settings, outlet_id)

    # Phase F path (network) — left as a clear TODO.
    raise NotImplementedError(
        f"Live scraping for {outlet_id} not implemented (Phase F); "
        "set USE_MOCKS=true to use fixtures."
    )
