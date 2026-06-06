"""Twitter/X adapter.

Mock reads canned fixtures; the real client (Phase F) wraps twitterapi.io
(pay-as-you-go). Methods return data normalized for `source_items` upserts so the
server layer stays thin.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import Settings


class TwitterAPI(ABC):
    @abstractmethod
    def monitor_accounts(self, accounts: list[str]) -> list[dict[str, Any]]:
        """Latest tweets from the monitored accounts, normalized to source_items."""

    @abstractmethod
    def get_trends(self, woeid: int) -> list[str]:
        """Trending topics for a WOEID (Argentina/Buenos Aires = 455827)."""

    @abstractmethod
    def search(self, query: str) -> list[dict[str, Any]]:
        """Most-interacted tweets for a topic/keyword, normalized to source_items."""

    @abstractmethod
    def publish(self, text: str, scheduled_at: str | None = None) -> dict[str, Any]:
        """Publish (or accept a scheduled publish for) a tweet. Returns {external_id, ...}."""


def _tweet_to_item(t: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "tweet",
        "source": t.get("handle", "unknown"),
        "title": None,
        "body": t.get("text", ""),
        "url": t.get("url"),
        "author": t.get("author") or t.get("handle"),
        "section": None,
        "published_at": t.get("created_at"),
        "dedupe_key": f"tweet:{t['id']}",
        "raw": t,
    }


class MockTwitterAPI(TwitterAPI):
    """Reads fixtures/twitter/{timeline,trends}.json. No network."""

    def __init__(self, fixtures_dir: Path):
        self._dir = fixtures_dir / "twitter"

    def _load(self, name: str, default: Any) -> Any:
        path = self._dir / name
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))

    def monitor_accounts(self, accounts: list[str]) -> list[dict[str, Any]]:
        tweets = self._load("timeline.json", [])
        if accounts:
            tweets = [t for t in tweets if t.get("handle") in accounts] or tweets
        return [_tweet_to_item(t) for t in tweets]

    def get_trends(self, woeid: int) -> list[str]:
        return self._load("trends.json", [])

    def search(self, query: str) -> list[dict[str, Any]]:
        tweets = self._load("timeline.json", [])
        q = query.lower()
        hits = [t for t in tweets if q in t.get("text", "").lower()]
        return [_tweet_to_item(t) for t in hits]

    def publish(self, text: str, scheduled_at: str | None = None) -> dict[str, Any]:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        return {
            "external_id": f"mock-tweet-{stamp}",
            "scheduled_at": scheduled_at,
            "published": scheduled_at is None,
            "text": text,
        }


class RealTwitterAPI(TwitterAPI):
    """twitterapi.io client. TODO Phase F: implement against the REST API.

    Endpoints to wire (confirm against twitterapi.io docs):
      - user timeline / tweets-by-account  → monitor_accounts
      - trends by WOEID                     → get_trends
      - advanced search                     → search
      - create tweet                        → publish
    Billing is pay-as-you-go (~$0.15 / 1000 tweets).
    """

    def __init__(self, api_key: str):
        self.api_key = api_key

    def _todo(self, what: str) -> None:
        raise NotImplementedError(f"RealTwitterAPI.{what} not implemented (Phase F).")

    def monitor_accounts(self, accounts: list[str]) -> list[dict[str, Any]]:
        self._todo("monitor_accounts")
        return []

    def get_trends(self, woeid: int) -> list[str]:
        self._todo("get_trends")
        return []

    def search(self, query: str) -> list[dict[str, Any]]:
        self._todo("search")
        return []

    def publish(self, text: str, scheduled_at: str | None = None) -> dict[str, Any]:
        self._todo("publish")
        return {}


def get_twitter(settings: Settings) -> TwitterAPI:
    if settings.use_mocks or not settings.twitterapi_io_key:
        return MockTwitterAPI(settings.fixtures)
    return RealTwitterAPI(settings.twitterapi_io_key)
