"""Media scrapers for the 5 monitored outlets.

Each outlet has its own subclass with TODO real selectors (Phase F). While
USE_MOCKS is true, `scrape_outlet` loads canned articles from
fixtures/outlets/<outlet_id>.json instead of hitting the network.
"""

from .base import NormalizedArticle, Scraper
from .outlets import OUTLETS, scrape_outlet

__all__ = ["NormalizedArticle", "Scraper", "OUTLETS", "scrape_outlet"]
