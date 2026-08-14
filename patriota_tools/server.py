"""patriota-tools — stdio MCP server exposing El Patriota's domain tools to Hermes.

Tools surface to the agent as ``mcp_patriota_<name>``. They handle I/O and
structured editorial state; the journalistic text itself is written by the Hermes
agent (Claude), guided by the editable prompts and the SKILL.md playbooks.

Run standalone for testing:  patriota-tools   (or: python -m patriota_tools.server)
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

import yaml
from mcp.server.fastmcp import Context, FastMCP

from . import storage as _storage  # noqa: F401  (ensures package import)
from .adapters.cms import get_cms
from .adapters.twitterapi import get_twitter
from .clustering import HybridClusterer
from .config import load_settings
from .generation import ArticleGenerator
from .scrapers import OUTLETS, scrape_outlet
from .storage import db

settings = load_settings()
db.init_db(settings.db_path)


def _seed_prompts() -> None:
    """Seed the editable prompts from hermes/prompts/*.md, keeping the DB in sync
    with repo changes until an editor customizes a prompt via Telegram.

    - No version yet → seed it (editor='seed').
    - Latest version is still editor='seed' and the repo file changed → seed a new
      version, so `git pull` + reinstall actually updates production prompts.
    - Latest version was authored by an editor (any other 'editor' value) → never
      touch it; their edit always wins over the repo default.
    """
    for name in ("editorial", "filtering", "twitter", "recheck", "working_hours"):
        path = settings.prompts / f"{name}.md"
        if not path.exists():
            continue
        file_content = path.read_text(encoding="utf-8")

        latest = db.get_latest_prompt(settings.db_path, name)
        if latest is None:
            db.add_prompt_version(settings.db_path, name, file_content, editor="seed")
        elif latest.get("editor") == "seed" and latest.get("content") != file_content:
            db.add_prompt_version(settings.db_path, name, file_content, editor="seed")


_seed_prompts()

mcp = FastMCP("patriota")


# ── helpers ─────────────────────────────────────────────────────────────────────
def _load_sources() -> dict[str, Any]:
    path = settings.sources
    if not path.exists():
        return {"x_accounts": [], "outlets": []}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


# Argentina has no DST — a fixed UTC-3 offset is the local Buenos Aires time.
_BUE_TZ = timezone(timedelta(hours=-3))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_bue_str() -> str:
    """Current Buenos Aires local time as 'YYYY-MM-DD HH:MM:SS' (for CMS 'fecha')."""
    return datetime.now(_BUE_TZ).strftime("%Y-%m-%d %H:%M:%S")


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
def fetch_prompt(name: str) -> dict[str, Any]:
    """Get the current version of an editorial prompt ('editorial'|'filtering'|'twitter').

    Always call this before proposing titles, filtering, or drafting so you use the
    editors' latest guidance.
    """
    latest = db.get_latest_prompt(settings.db_path, name)
    if latest:
        return latest
    path = settings.prompts / f"{name}.md"
    if path.exists():
        return {"name": name, "content": path.read_text(encoding="utf-8"), "note": "default (aún no personalizado)"}
    return {"name": name, "content": "", "note": "sin versión definida todavía"}


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


# ── schedule / working hours ─────────────────────────────────────────────────────
@mcp.tool()
def get_schedule_status() -> dict[str, Any]:
    """Check if current Buenos Aires time (UTC-3) falls within editorial working hours.

    Reads the 'working_hours' prompt (format 'HH:MM-HH:MM'). '00:00' as end = midnight.
    Editors can change the window via /editar-prompt working_hours [HH:MM-HH:MM].
    Returns in_working_hours bool plus current time and configured window for transparency.
    """
    prompt = db.get_latest_prompt(settings.db_path, "working_hours")
    window = (prompt or {}).get("content", "07:00-00:00").strip().splitlines()[0].strip()

    now_bue = datetime.now(_BUE_TZ)
    now_minutes = now_bue.hour * 60 + now_bue.minute

    try:
        start_str, end_str = window.split("-")
        sh, sm = map(int, start_str.strip().split(":"))
        eh, em = map(int, end_str.strip().split(":"))
        start_min = sh * 60 + sm
        end_min = eh * 60 + em
        if end_min == 0:  # "00:00" means midnight = end of day
            end_min = 24 * 60
        in_window = start_min <= now_minutes < end_min
    except Exception:
        in_window = True  # fail open: don't silently block editorial on a parse error
        window = f"(parse error: {window!r})"

    return {
        "in_working_hours": in_window,
        "window_bue": window,
        "now_bue": now_bue.strftime("%H:%M"),
        "day": now_bue.strftime("%A"),
    }


# ── ingest write queue ───────────────────────────────────────────────────────────
# All SQLite inserts from ingestion go through a single background worker so
# writes are never concurrent (SQLite allows only one writer at a time even in
# WAL mode). The worker stays alive for the lifetime of the MCP process; items
# enqueued before a tool-call timeout are still written after the call returns.

_ingest_queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
_worker_task: asyncio.Task | None = None


async def _db_writer_worker() -> None:
    while True:
        item = await _ingest_queue.get()
        if item is None:  # shutdown sentinel
            _ingest_queue.task_done()
            return
        try:
            db.upsert_source_item(settings.db_path, item)
        except Exception:
            pass  # IntegrityError on dedupe is expected; swallow all to keep draining
        finally:
            _ingest_queue.task_done()


async def _ensure_writer() -> None:
    global _worker_task
    if _worker_task is None or _worker_task.done():
        _worker_task = asyncio.create_task(_db_writer_worker())


# ── ingestion ───────────────────────────────────────────────────────────────────

_TWITTER_CHUNK = 20  # accounts per progress batch


@mcp.tool()
async def ingest_twitter(ctx: Context) -> dict[str, Any]:
    """Pull latest tweets from all monitored accounts (concurrent, reports progress).

    Fetches in batches of 20 with up to 10 parallel requests per batch.
    Emits a progress notification after each batch (~every 3 s for real API).
    Items are written to DB via the ingest queue (sequential, no lock contention).
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

    await _ensure_writer()
    for it in all_items:
        await _ingest_queue.put(it)
    await _ingest_queue.join()
    return {"fetched": len(all_items), "kind": "tweet", "accounts": total}


@mcp.tool()
def get_trends() -> list[str]:
    """Trending topics for Argentina/Buenos Aires (WOEID 455827)."""
    return get_twitter(settings).get_trends(settings.woeid)


@mcp.tool()
def search_twitter(
    query: str,
    query_type: str = "Latest",
    count: int = 20,
) -> list[dict[str, Any]]:
    """Search tweets by keyword or account.

    Use ``from:handle`` to get tweets from a specific account (e.g. ``from:jmilei``).
    query_type: 'Latest' (default, chronological) or 'Top' (most-engaged).
    count: max results to return (default 20).
    Handles in from: are normalised to lowercase automatically.
    """
    return get_twitter(settings).search(query, query_type=query_type, count=count)


@mcp.tool()
async def ingest_media(outlet_id: str | None = None) -> dict[str, Any]:
    """Scrape one outlet (by id) or all outlets; store new (deduped) articles.

    Scraping runs concurrently (one thread per outlet, each bounded by the scraper's
    own HTTP timeout) so a single stalled outlet costs seconds, not the whole call.
    Items are written to DB via the ingest queue (sequential, no lock contention).
    """
    outlet_ids = [outlet_id] if outlet_id else list(OUTLETS.keys())
    results = await asyncio.gather(
        *(asyncio.to_thread(scrape_outlet, settings, oid) for oid in outlet_ids)
    )
    all_items: list[dict[str, Any]] = [item for items in results for item in items]

    await _ensure_writer()
    for it in all_items:
        await _ingest_queue.put(it)
    await _ingest_queue.join()
    return {"outlets": outlet_ids, "fetched": len(all_items), "kind": "article"}


@mcp.tool()
async def ingest_all(ctx: Context) -> dict[str, Any]:
    """Full monitoring tick: fetches tweets and articles in parallel, writes to DB sequentially.

    HTTP fetching (slow) runs concurrently for both sources. All items are written
    to DB through the shared ingest queue so writes never overlap.
    """
    tw, md = await asyncio.gather(
        ingest_twitter(ctx),
        ingest_media(),
    )
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
    """List clusters, optionally by status (proposed|titled|approved|rejected|expired).

    'proposed' clusters have no article yet. 'titled' is set automatically by
    create_article the moment a title is proposed for a cluster — a cluster never
    goes back to 'proposed' after that, regardless of what happens to its article
    (approved, discarded, or expired), so the same story is never re-proposed.
    """
    return db.list_clusters(settings.db_path, status=status)


@mcp.tool()
def get_cluster(cluster_id: int) -> dict[str, Any]:
    """A cluster with its source items (titles, bodies, URLs) for drafting context."""
    cluster = db.get_cluster(settings.db_path, cluster_id)
    return cluster or {"error": f"cluster {cluster_id} no existe"}


@mcp.tool()
def set_cluster_status(cluster_id: int, status: str) -> dict[str, Any]:
    """Set a cluster status (proposed|titled|approved|rejected|expired)."""
    db.set_cluster_status(settings.db_path, cluster_id, status)
    return {"ok": True, "cluster_id": cluster_id, "status": status}


# ── semantic clustering ──────────────────────────────────────────────────────────
@mcp.tool()
def cluster_items_semantically(item_ids: list[int] | None = None) -> dict[str, Any]:
    """Group unprocessed items using embeddings (text-embedding-3-small) + HDBSCAN +
    LLM validation. If item_ids is None, processes all items with status 'new' or 'solo'.
    Creates validated clusters in the DB; marks noise items as 'solo' for the next cycle.
    Requires OPENAI_API_KEY and OPENROUTER_API_KEY in the environment.
    """
    if not settings.openai_api_key:
        return {"error": "OPENAI_API_KEY no configurado"}
    if not settings.openrouter_api_key:
        return {"error": "OPENROUTER_API_KEY no configurado"}

    if item_ids is not None:
        items = [
            it for it in db.list_unprocessed_items(settings.db_path, limit=500)
            if it["id"] in set(item_ids)
        ]
    else:
        items = db.list_unprocessed_items(settings.db_path)

    if not items:
        return {"clusters_created": 0, "noise_items": 0, "cluster_ids": [], "note": "sin ítems nuevos"}

    clusterer = HybridClusterer(settings.openai_api_key, settings.openrouter_api_key)
    result = clusterer.run(items)

    cluster_ids: list[int] = []
    for cluster in result["validated_clusters"]:
        cid = db.create_cluster(settings.db_path, cluster["tema"], cluster["item_ids"])
        cluster_ids.append(cid)

    db.mark_items_solo(settings.db_path, result["noise_item_ids"])

    return {
        "clusters_created": len(cluster_ids),
        "noise_items": len(result["noise_item_ids"]),
        "cluster_ids": cluster_ids,
    }


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
    """Update an article's fields/status.

    Lifecycle: title_proposed → summary_proposed → (summary_approved, internal) → published | rejected.
    summary_approved is set automatically by publish_article_to_cms — don't set it manually.
    """
    fields = {k: v for k, v in dict(title=title, summary=summary, body=body, status=status).items() if v is not None}
    db.update_article(settings.db_path, article_id, **fields)
    return {"ok": True, "article_id": article_id, "updated": list(fields)}


@mcp.tool()
def get_article(article_id: int) -> dict[str, Any]:
    """Get one article record."""
    article = db.get_article(settings.db_path, article_id)
    return article or {"error": f"artículo {article_id} no existe"}


@mcp.tool()
def get_article_sources(article_id: int) -> dict[str, Any]:
    """The exact source items (tweets/articles) used to write an article's draft.

    Resolves article -> cluster -> cluster_items -> source_items directly in the DB —
    the same path the generation pipeline reads from. Always use this to answer
    "what sources back article N" instead of recalling the cluster_id from earlier
    in the conversation; that's how sources get cross-wired between articles.
    """
    result = db.get_article_sources(settings.db_path, article_id)
    return result or {"error": f"artículo {article_id} no existe"}


@mcp.tool()
def get_articles_sources(article_ids: list[int]) -> dict[str, Any]:
    """Batch get_article_sources — sources for several articles at once, keyed by article_id."""
    return {str(aid): get_article_sources(aid) for aid in article_ids}


@mcp.tool()
def list_articles(status: str | None = None) -> list[dict[str, Any]]:
    """List articles, optionally by status."""
    return db.list_articles(settings.db_path, status=status)


@mcp.tool()
def expire_stale_articles(max_age_hours: int = 12) -> dict[str, Any]:
    """Retire proposed titles the editors never acted on (status → 'expired').

    Flips any article left in 'title_proposed' for more than max_age_hours (default 12)
    to the terminal 'expired' status, so old proposals stop reappearing in the digest and
    article IDs stop piling up. Rows are kept (not deleted) for traceability. Call this at
    the START of a monitoreo tick — during working hours only — before listing titles.
    """
    ids = db.expire_stale_articles(settings.db_path, max_age_hours)
    return {"expired": len(ids), "article_ids": ids}


def _generate_draft(article: dict[str, Any]) -> dict[str, Any]:
    """Run the two-prompt generation pipeline for an article and persist the result.

    Mutates `article` in place with the generated fields so the caller can use them
    immediately (e.g. to build the CMS payload) without a second DB read.
    """
    cluster = db.get_cluster(settings.db_path, article["cluster_id"]) if article.get("cluster_id") else None
    items = (cluster or {}).get("items", [])
    if not items:
        return {"error": "el cluster asociado no tiene fuentes"}

    editorial_prompt_row = db.get_latest_prompt(settings.db_path, "editorial")
    recheck_prompt_row = db.get_latest_prompt(settings.db_path, "recheck")
    editorial_prompt = (editorial_prompt_row or {}).get("content", "")
    recheck_prompt = (recheck_prompt_row or {}).get("content", "Rechequear y humanizar el siguiente borrador.")

    # Pass the approved title as a hard constraint for the LLM.
    full_prompt = f"TÍTULO APROBADO (usalo exactamente): {article['title']}\n\n{editorial_prompt}"

    generator = ArticleGenerator(settings.openrouter_api_key)
    generated = generator.generate(items, full_prompt, recheck_prompt)

    db.update_article(
        settings.db_path, article["id"],
        title=generated["titulo"] or article["title"],
        bajada=generated["bajada"],
        volanta=generated["volanta"],
        body=generated["body_text"],
    )
    article.update(
        title=generated["titulo"] or article["title"],
        bajada=generated["bajada"],
        volanta=generated["volanta"],
        body=generated["body_text"],
    )
    return {"ok": True}


@mcp.tool()
def publish_article_to_cms(article_id: int) -> dict[str, Any]:
    """Approve the summary, generate the full draft, and publish it to the CMS — one atomic step.

    Call this for /publicar on an article in 'summary_proposed'. It advances the article
    to 'summary_approved', runs the two-prompt draft pipeline (generation → recheck) against
    the approved title and cluster sources, then posts the result to the CMS as 'borrador'
    (visible=0) and marks the article 'published'.

    Retry-safe: if a previous call generated the draft but the CMS post failed, the article
    is left in 'summary_approved' with its body already saved — calling this again skips
    regeneration and just retries the CMS post. Requires OPENROUTER_API_KEY.
    """
    article = db.get_article(settings.db_path, article_id)
    if not article:
        return {"error": f"artículo {article_id} no existe"}

    status = article.get("status")
    if status not in ("summary_proposed", "summary_approved"):
        return {
            "error": (
                f"el artículo debe estar en summary_proposed o summary_approved para publicar "
                f"(estado actual: {status})"
            )
        }

    if status == "summary_proposed":
        db.update_article(settings.db_path, article_id, status="summary_approved")
        article["status"] = "summary_approved"

    if not article.get("body"):
        if not settings.openrouter_api_key:
            return {"error": "OPENROUTER_API_KEY no configurado"}
        gen_result = _generate_draft(article)
        if "error" in gen_result:
            return gen_result

    prompt = db.get_latest_prompt(settings.db_path, "editorial")
    prompt_version_id = prompt["id"] if prompt else None

    payload = {
        "fecha": _now_bue_str(),
        "titulo": article["title"],
        "bajada": article.get("bajada") or article.get("summary") or "",
        "texto": article.get("body") or "",
        "autor": "El Patriota",
        "volanta": article.get("volanta") or "",
    }
    try:
        result = get_cms(settings).publish_draft(payload)
    except Exception as exc:
        return {
            "error": (
                f"fallo al publicar en el CMS: {exc}. El borrador quedó guardado "
                f"(estado summary_approved) — reintentá con /publicar."
            )
        }

    db.update_article(
        settings.db_path, article_id,
        status="published", cms_id=result.get("cms_id"),
        prompt_version_id=prompt_version_id,
    )
    return {
        "ok": True,
        "article_id": article_id,
        "titulo": article["title"],
        "bajada": article.get("bajada"),
        "cms": result,
    }


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


@mcp.tool()
def reject_tweet(tweet_id: int) -> dict[str, Any]:
    """Mark a proposed tweet as rejected so it no longer appears in the pending list."""
    db.update_tweet(settings.db_path, tweet_id, status="rejected")
    return {"ok": True, "tweet_id": tweet_id, "status": "rejected"}


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
