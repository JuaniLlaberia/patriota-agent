"""Twitter/X adapter.

Mock reads canned fixtures; the real client wraps twitterapi.io (pay-as-you-go,
$0.15/1k tweets). Only monitoring is implemented — tweet publishing is out of scope
for the current phase and raises NotImplementedError.
"""

from __future__ import annotations

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from ..config import Settings

logger = logging.getLogger(__name__)

_TWITTERAPI_BASE = "https://api.twitterapi.io"


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


# ── normalization ────────────────────────────────────────────────────────────────

def _tweet_to_item(t: dict[str, Any]) -> dict[str, Any]:
    """Normalize a mock-fixture tweet to a source_item."""
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


def _api_tweet_to_item(tweet: dict[str, Any]) -> dict[str, Any]:
    """Normalize a twitterapi.io response tweet to a source_item."""
    author = tweet.get("author") or {}
    handle = author.get("userName", "unknown")
    return {
        "kind": "tweet",
        "source": handle,
        "title": None,
        "body": tweet.get("text", ""),
        "url": tweet.get("url"),
        "author": author.get("name") or handle,
        "section": None,
        "published_at": tweet.get("createdAt"),
        "dedupe_key": f"tweet:{tweet['id']}",
        "raw": tweet,
    }


# ── mock ─────────────────────────────────────────────────────────────────────────

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


# ── real ─────────────────────────────────────────────────────────────────────────

async def _fetch_accounts_concurrent(
    api_key: str, accounts: list[str], max_concurrent: int = 10
) -> list[dict[str, Any]]:
    """Fetch last tweets for a list of handles concurrently (max_concurrent at a time)."""
    sem = asyncio.Semaphore(max_concurrent)

    async def _one(client: httpx.AsyncClient, handle: str) -> list[dict[str, Any]]:
        async with sem:
            try:
                r = await client.get("/twitter/user/last_tweets", params={"userName": handle})
                r.raise_for_status()
                return [_api_tweet_to_item(t) for t in r.json().get("tweets", [])]
            except Exception as exc:
                logger.warning("Failed to fetch tweets for @%s: %s", handle, exc)
                return []

    async with httpx.AsyncClient(
        base_url=_TWITTERAPI_BASE,
        headers={"X-API-Key": api_key},
        timeout=15.0,
    ) as client:
        results = await asyncio.gather(*[_one(client, h) for h in accounts])

    return [item for batch in results for item in batch]


class RealTwitterAPI(TwitterAPI):
    """twitterapi.io client (read-only monitoring).

    Auth: X-API-Key header.
    Endpoints used:
      GET /twitter/user/last_tweets  → monitor_accounts
      GET /twitter/trends            → get_trends
      GET /twitter/tweet/advanced_search → search
    """

    def __init__(self, api_key: str):
        self._api_key = api_key
        self._client = httpx.Client(
            base_url=_TWITTERAPI_BASE,
            headers={"X-API-Key": api_key},
            timeout=15.0,
        )

    def monitor_accounts(self, accounts: list[str]) -> list[dict[str, Any]]:
        # Runs all requests concurrently (max 10 in parallel) via a fresh event loop.
        # 111 sequential × ~1.5 s → ~17 s total with concurrency=10.
        return asyncio.run(_fetch_accounts_concurrent(self._api_key, accounts))

    def get_trends(self, woeid: int) -> list[str]:
        try:
            resp = self._client.get("/twitter/trends", params={"woeid": woeid})
            resp.raise_for_status()
            return [t["name"] for t in resp.json().get("trends", [])]
        except Exception as exc:
            logger.warning("Failed to fetch trends (woeid=%s): %s", woeid, exc)
            return []

    def search(self, query: str) -> list[dict[str, Any]]:
        try:
            resp = self._client.get(
                "/twitter/tweet/advanced_search",
                params={"query": query, "queryType": "Top"},
            )
            resp.raise_for_status()
            return [_api_tweet_to_item(t) for t in resp.json().get("tweets", [])]
        except Exception as exc:
            logger.warning("Twitter search failed for %r: %s", query, exc)
            return []

    def publish(self, text: str, scheduled_at: str | None = None) -> dict[str, Any]:
        raise NotImplementedError(
            "Tweet publishing is out of scope for the current phase. "
            "Implement via Twitter API v2 (OAuth 2.0) when ready."
        )


# ── factory ──────────────────────────────────────────────────────────────────────

def get_twitter(settings: Settings) -> TwitterAPI:
    if settings.use_mocks or not settings.twitterapi_io_key:
        return MockTwitterAPI(settings.fixtures)
    return RealTwitterAPI(settings.twitterapi_io_key)
