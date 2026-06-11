"""patriota-tools — stdio MCP server exposing El Patriota's domain tools to Hermes.

Tools surface to the agent as ``mcp_patriota_<name>``. They handle I/O and
structured editorial state; the journalistic text itself is written by the Hermes
agent (Claude), guided by the editable prompts and the SKILL.md playbooks.

Run standalone for testing:  patriota-tools   (or: python -m patriota_tools.server)
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import yaml
from mcp.server.fastmcp import Context, FastMCP

from . import storage as _storage  # noqa: F401  (ensures package import)
from .adapters.cms import get_cms
from .adapters.twitterapi import get_twitter
from .config import load_settings
from .scrapers import OUTLETS, scrape_outlet
from .storage import db

settings = load_settings()
db.init_db(settings.db_path)


def _seed_prompts() -> None:
    """Seed the 3 editable prompts from hermes/prompts/*.md if none exist yet."""
    for name in ("editorial", "filtering", "twitter"):
        if db.get_latest_prompt(settings.db_path, name):
            continue
        path = settings.prompts / f"{name}.md"
        if path.exists():
            db.add_prompt_version(
                settings.db_path, name, path.read_text(encoding="utf-8"), editor="seed"
            )


_seed_prompts()

mcp = FastMCP("patriota")


# ── helpers ─────────────────────────────────────────────────────────────────────
def _load_sources() -> dict[str, Any]:
    path = settings.sources
    if not path.exists():
        return {"x_accounts": [], "outlets": []}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── meta / config ────────────────────────────────────────────────────────────────
@mcp.tool()
def ping() -> str:
    """Health check. Returns 'pong' plus whether mocks are active."""
    return f"pong (use_mocks={settings.use_mocks})"


@mcp.tool()
def sources() -> dict[str, Any]:
    """The configured 50 X/Twitter accounts and 5 media outlet ids to monitor."""
    return _load_sources()


# ── editable editorial prompts (editorial | filtering | twitter) ─────────────────
@mcp.tool()
def get_prompt(name: str) -> dict[str, Any]:
    """Get the current version of an editorial prompt ('editorial'|'filtering'|'twitter').

    Always call this before proposing titles, filtering, or drafting so you use the
    editors' latest guidance.
    """
    latest = db.get_latest_prompt(settings.db_path, name)
    return latest or {"name": name, "content": "", "note": "sin versión definida todavía"}


@mcp.tool()
def set_prompt(name: str, content: str, editor: str | None = None) -> dict[str, Any]:
    """Save a NEW version of an editorial prompt (rollback + trazabilidad).

    Use when an editor runs /prompt-editorial, /prompt-filtrado or /prompt-twitter.
    """
    version_id = db.add_prompt_version(settings.db_path, name, content, editor)
    return {"ok": True, "name": name, "version_id": version_id}


@mcp.tool()
def list_prompt_versions(name: str) -> list[dict[str, Any]]:
    """History of all saved versions of an editorial prompt."""
    return db.list_prompt_versions(settings.db_path, name)


# ── ingestion ───────────────────────────────────────────────────────────────────

_TWITTER_CHUNK = 20  # accounts per progress batch


@mcp.tool()
async def ingest_twitter(ctx: Context) -> dict[str, Any]:
    """Pull latest tweets from all monitored accounts (concurrent, reports progress).

    Fetches in batches of 20 with up to 10 parallel requests per batch.
    Emits a progress notification after each batch (~every 3 s for real API).
    """
    accounts = [a if isinstance(a, str) else a.get("handle") for a in _load_sources().get("x_accounts", [])]
    accounts = [a for a in accounts if a]
    total = len(accounts)
    tw = get_twitter(settings)
    all_items: list[dict[str, Any]] = []

    for start in range(0, total, _TWITTER_CHUNK):
        batch = accounts[start : start + _TWITTER_CHUNK]
        # monitor_accounts runs concurrent HTTP internally (asyncio.run + semaphore);
        # to_thread avoids blocking the MCP event loop while it does so.
        chunk_items = await asyncio.to_thread(tw.monitor_accounts, batch)
        all_items.extend(chunk_items)
        await ctx.report_progress(min(start + _TWITTER_CHUNK, total), total)

    new = sum(1 for it in all_items if db.upsert_source_item(settings.db_path, it))
    return {"fetched": len(all_items), "new": new, "kind": "tweet", "accounts": total}


@mcp.tool()
def get_trends() -> list[str]:
    """Trending topics for Argentina/Buenos Aires (WOEID 455827)."""
    return get_twitter(settings).get_trends(settings.woeid)


@mcp.tool()
def search_twitter(query: str) -> list[dict[str, Any]]:
    """Most-interacted tweets for a topic/keyword (normalized, not yet stored)."""
    return get_twitter(settings).search(query)


@mcp.tool()
def ingest_media(outlet_id: str | None = None) -> dict[str, Any]:
    """Scrape one outlet (by id) or all outlets; store new (deduped) articles."""
    outlet_ids = [outlet_id] if outlet_id else list(OUTLETS.keys())
    fetched = new = 0
    for oid in outlet_ids:
        items = scrape_outlet(settings, oid)
        fetched += len(items)
        new += sum(1 for it in items if db.upsert_source_item(settings.db_path, it))
    return {"outlets": outlet_ids, "fetched": fetched, "new": new, "kind": "article"}


@mcp.tool()
async def ingest_all(ctx: Context) -> dict[str, Any]:
    """Full monitoring tick: tweets from all accounts + articles from all outlets."""
    tw = await ingest_twitter(ctx)
    md = ingest_media()
    return {"twitter": tw, "media": md, "at": _now()}


@mcp.tool()
def list_new_items(kind: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    """List ingested items not yet grouped (status='new'). Optionally filter by kind."""
    return db.list_source_items(settings.db_path, status="new", kind=kind, limit=limit)


# ── clustering (min 2 sources per cluster, per spec) ─────────────────────────────
@mcp.tool()
def create_cluster(topic: str, item_ids: list[int]) -> dict[str, Any]:
    """Group related source items (min 2) under a topic. Marks items as clustered."""
    if len(item_ids) < 2:
        return {"ok": False, "error": "un cluster necesita al menos 2 fuentes"}
    cluster_id = db.create_cluster(settings.db_path, topic, item_ids)
    return {"ok": True, "cluster_id": cluster_id, "topic": topic, "items": item_ids}


@mcp.tool()
def list_clusters(status: str | None = None) -> list[dict[str, Any]]:
    """List clusters, optionally by status (proposed|approved|rejected)."""
    return db.list_clusters(settings.db_path, status=status)


@mcp.tool()
def get_cluster(cluster_id: int) -> dict[str, Any]:
    """A cluster with its source items (titles, bodies, URLs) for drafting context."""
    cluster = db.get_cluster(settings.db_path, cluster_id)
    return cluster or {"error": f"cluster {cluster_id} no existe"}


@mcp.tool()
def set_cluster_status(cluster_id: int, status: str) -> dict[str, Any]:
    """Set a cluster status (proposed|approved|rejected)."""
    db.set_cluster_status(settings.db_path, cluster_id, status)
    return {"ok": True, "cluster_id": cluster_id, "status": status}


# ── article pipeline ─────────────────────────────────────────────────────────────
@mcp.tool()
def create_article(title: str, cluster_id: int | None = None) -> dict[str, Any]:
    """Create an article record in 'title_proposed' state for a proposed title."""
    article_id = db.create_article(settings.db_path, title, cluster_id)
    return {"ok": True, "article_id": article_id, "status": "title_proposed"}


@mcp.tool()
def update_article(
    article_id: int,
    title: str | None = None,
    summary: str | None = None,
    body: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    """Update an article's fields/status (title_proposed→summary_approved→published)."""
    fields = {k: v for k, v in dict(title=title, summary=summary, body=body, status=status).items() if v is not None}
    db.update_article(settings.db_path, article_id, **fields)
    return {"ok": True, "article_id": article_id, "updated": list(fields)}


@mcp.tool()
def get_article(article_id: int) -> dict[str, Any]:
    """Get one article record."""
    article = db.get_article(settings.db_path, article_id)
    return article or {"error": f"artículo {article_id} no existe"}


@mcp.tool()
def list_articles(status: str | None = None) -> list[dict[str, Any]]:
    """List articles, optionally by status."""
    return db.list_articles(settings.db_path, status=status)


@mcp.tool()
def publish_article_to_cms(article_id: int) -> dict[str, Any]:
    """Publish an approved article to the CMS as 'borrador' with trazabilidad.

    Only call after the editor has approved the full draft. Builds the payload with
    source URLs, timestamp and the editorial prompt version, posts to the CMS, and
    marks the article 'published'.
    """
    article = db.get_article(settings.db_path, article_id)
    if not article:
        return {"error": f"artículo {article_id} no existe"}
    if not article.get("body"):
        return {"error": "el artículo no tiene cuerpo redactado todavía"}

    fuentes: list[str] = []
    if article.get("cluster_id"):
        cluster = db.get_cluster(settings.db_path, article["cluster_id"])
        if cluster:
            fuentes = [it.get("url") for it in cluster["items"] if it.get("url")]

    prompt = db.get_latest_prompt(settings.db_path, "editorial")
    prompt_version_id = prompt["id"] if prompt else None

    payload = {
        "titulo": article["title"],
        "bajada": article.get("summary") or "",
        "cuerpo": article["body"],
        "tags": [],
        "estado": "borrador",
        "trazabilidad": {
            "fuentes": fuentes,
            "timestamp": _now(),
            "prompt_version": prompt_version_id,
        },
    }
    result = get_cms(settings).publish_draft(payload)
    db.update_article(
        settings.db_path, article_id,
        status="published", cms_id=result.get("cms_id"),
        prompt_version_id=prompt_version_id,
    )
    return {"ok": True, "article_id": article_id, "cms": result}


# ── tweets ───────────────────────────────────────────────────────────────────────
@mcp.tool()
def propose_tweet(text: str) -> dict[str, Any]:
    """Record a proposed tweet (status 'proposed') awaiting editor approval."""
    tweet_id = db.create_tweet(settings.db_path, text)
    return {"ok": True, "tweet_id": tweet_id, "status": "proposed"}


@mcp.tool()
def approve_tweet(tweet_id: int, scheduled_at: str | None = None) -> dict[str, Any]:
    """Approve a tweet. With scheduled_at (ISO 8601) it is queued for later publish.

    For a scheduled tweet, ALSO create a Hermes cron one-shot at the same ISO time
    whose job calls publish_tweet(tweet_id). Without scheduled_at, publish now.
    """
    status = "scheduled" if scheduled_at else "approved"
    db.update_tweet(settings.db_path, tweet_id, status=status, scheduled_at=scheduled_at)
    return {"ok": True, "tweet_id": tweet_id, "status": status, "scheduled_at": scheduled_at}


@mcp.tool()
def publish_tweet(tweet_id: int) -> dict[str, Any]:
    """Publish an approved/scheduled tweet via the Twitter adapter; mark it published."""
    tweets = {t["id"]: t for t in db.list_tweets(settings.db_path)}
    tweet = tweets.get(tweet_id)
    if not tweet:
        return {"error": f"tweet {tweet_id} no existe"}
    if tweet["status"] not in {"approved", "scheduled"}:
        return {"error": f"el tweet {tweet_id} no está aprobado (estado={tweet['status']})"}
    result = get_twitter(settings).publish(tweet["text"], tweet.get("scheduled_at"))
    db.update_tweet(
        settings.db_path, tweet_id,
        status="published", published_at=_now(), external_id=result.get("external_id"),
    )
    return {"ok": True, "tweet_id": tweet_id, "result": result}


@mcp.tool()
def list_tweets(status: str | None = None) -> list[dict[str, Any]]:
    """List tweets, optionally by status (proposed|approved|scheduled|published|rejected)."""
    return db.list_tweets(settings.db_path, status=status)


# ── editor message log ──────────────────────────────────────────────────────────
@mcp.tool()
def log_editor(direction: str, text: str) -> dict[str, Any]:
    """Log an editor interaction ('in' from editor, 'out' from Hermes) for the record."""
    db.log_message(settings.db_path, direction, text)
    return {"ok": True}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
