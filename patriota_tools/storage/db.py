"""SQLite schema + helpers for editorial state and traceability.

Low-volume MVP: each call opens a short-lived connection. Tables:
  source_items     ingested tweets/articles (deduped)
  clusters         semantic groupings (+ cluster_items join)
  articles         editorial pipeline state machine
  tweets           proposed/scheduled/published social posts
  prompt_versions  every edit to the 3 editable prompts (rollback + trazabilidad)
  editor_log       inbound/outbound editor messages
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS source_items (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    kind          TEXT NOT NULL,                       -- 'tweet' | 'article'
    source        TEXT NOT NULL,                       -- account handle or outlet id
    title         TEXT,
    body          TEXT,
    url           TEXT,
    author        TEXT,
    section       TEXT,
    published_at  TEXT,
    dedupe_key    TEXT UNIQUE NOT NULL,
    raw           TEXT,                                -- json
    status        TEXT NOT NULL DEFAULT 'new',         -- 'new' | 'clustered'
    ingested_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS clusters (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    topic       TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'proposed',      -- proposed|approved|rejected
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cluster_items (
    cluster_id  INTEGER NOT NULL,
    item_id     INTEGER NOT NULL,
    PRIMARY KEY (cluster_id, item_id),
    FOREIGN KEY (cluster_id) REFERENCES clusters(id),
    FOREIGN KEY (item_id)   REFERENCES source_items(id)
);

CREATE TABLE IF NOT EXISTS articles (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    cluster_id         INTEGER,
    title              TEXT NOT NULL,
    summary            TEXT,
    body               TEXT,
    status             TEXT NOT NULL DEFAULT 'title_proposed',
                       -- title_proposed | summary_approved | published | rejected
    cms_id             TEXT,
    prompt_version_id  INTEGER,
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL,
    FOREIGN KEY (cluster_id) REFERENCES clusters(id),
    FOREIGN KEY (prompt_version_id) REFERENCES prompt_versions(id)
);

CREATE TABLE IF NOT EXISTS tweets (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    text          TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'proposed',    -- proposed|approved|scheduled|published|rejected
    scheduled_at  TEXT,
    published_at  TEXT,
    external_id   TEXT,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS prompt_versions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,                         -- editorial|filtering|twitter
    content     TEXT NOT NULL,
    editor      TEXT,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS editor_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    direction   TEXT NOT NULL,                         -- 'in' | 'out'
    text        TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_conn(db_path: str) -> sqlite3.Connection:
    Path(db_path).expanduser().parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(db_path: str) -> None:
    with get_conn(db_path) as conn:
        conn.executescript(SCHEMA)


def _rows(cur: sqlite3.Cursor) -> list[dict[str, Any]]:
    return [dict(r) for r in cur.fetchall()]


# ── source_items ────────────────────────────────────────────────────────────────
def upsert_source_item(db_path: str, item: dict[str, Any]) -> bool:
    """Insert a normalized item; returns True if new, False if a dup was skipped."""
    with get_conn(db_path) as conn:
        try:
            conn.execute(
                """INSERT INTO source_items
                   (kind, source, title, body, url, author, section,
                    published_at, dedupe_key, raw, status, ingested_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?, 'new', ?)""",
                (
                    item["kind"], item["source"], item.get("title"), item.get("body"),
                    item.get("url"), item.get("author"), item.get("section"),
                    item.get("published_at"), item["dedupe_key"],
                    json.dumps(item.get("raw", {}), ensure_ascii=False), _now(),
                ),
            )
            return True
        except sqlite3.IntegrityError:
            return False  # duplicate dedupe_key


def list_source_items(
    db_path: str, status: str | None = None, kind: str | None = None, limit: int = 100
) -> list[dict[str, Any]]:
    q = "SELECT * FROM source_items WHERE 1=1"
    params: list[Any] = []
    if status:
        q += " AND status = ?"; params.append(status)
    if kind:
        q += " AND kind = ?"; params.append(kind)
    q += " ORDER BY ingested_at DESC LIMIT ?"; params.append(limit)
    with get_conn(db_path) as conn:
        return _rows(conn.execute(q, params))


# ── clusters ────────────────────────────────────────────────────────────────────
def create_cluster(db_path: str, topic: str, item_ids: list[int]) -> int:
    with get_conn(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO clusters (topic, status, created_at) VALUES (?, 'proposed', ?)",
            (topic, _now()),
        )
        cluster_id = int(cur.lastrowid)
        for item_id in item_ids:
            conn.execute(
                "INSERT OR IGNORE INTO cluster_items (cluster_id, item_id) VALUES (?, ?)",
                (cluster_id, item_id),
            )
            conn.execute(
                "UPDATE source_items SET status = 'clustered' WHERE id = ?", (item_id,)
            )
        return cluster_id


def set_cluster_status(db_path: str, cluster_id: int, status: str) -> None:
    with get_conn(db_path) as conn:
        conn.execute("UPDATE clusters SET status = ? WHERE id = ?", (status, cluster_id))


def list_clusters(db_path: str, status: str | None = None) -> list[dict[str, Any]]:
    q = "SELECT * FROM clusters"
    params: list[Any] = []
    if status:
        q += " WHERE status = ?"; params.append(status)
    q += " ORDER BY created_at DESC"
    with get_conn(db_path) as conn:
        return _rows(conn.execute(q, params))


def get_cluster(db_path: str, cluster_id: int) -> dict[str, Any] | None:
    with get_conn(db_path) as conn:
        row = conn.execute("SELECT * FROM clusters WHERE id = ?", (cluster_id,)).fetchone()
        if not row:
            return None
        cluster = dict(row)
        items = conn.execute(
            """SELECT si.* FROM source_items si
               JOIN cluster_items ci ON ci.item_id = si.id
               WHERE ci.cluster_id = ?""",
            (cluster_id,),
        )
        cluster["items"] = _rows(items)
        return cluster


# ── articles ────────────────────────────────────────────────────────────────────
def create_article(db_path: str, title: str, cluster_id: int | None = None) -> int:
    with get_conn(db_path) as conn:
        cur = conn.execute(
            """INSERT INTO articles (cluster_id, title, status, created_at, updated_at)
               VALUES (?, ?, 'title_proposed', ?, ?)""",
            (cluster_id, title, _now(), _now()),
        )
        return int(cur.lastrowid)


_ARTICLE_FIELDS = {"title", "summary", "body", "status", "cms_id", "prompt_version_id"}


def update_article(db_path: str, article_id: int, **fields: Any) -> None:
    updates = {k: v for k, v in fields.items() if k in _ARTICLE_FIELDS}
    if not updates:
        return
    cols = ", ".join(f"{k} = ?" for k in updates)
    with get_conn(db_path) as conn:
        conn.execute(
            f"UPDATE articles SET {cols}, updated_at = ? WHERE id = ?",
            (*updates.values(), _now(), article_id),
        )


def get_article(db_path: str, article_id: int) -> dict[str, Any] | None:
    with get_conn(db_path) as conn:
        row = conn.execute("SELECT * FROM articles WHERE id = ?", (article_id,)).fetchone()
        return dict(row) if row else None


def list_articles(db_path: str, status: str | None = None) -> list[dict[str, Any]]:
    q = "SELECT * FROM articles"
    params: list[Any] = []
    if status:
        q += " WHERE status = ?"; params.append(status)
    q += " ORDER BY updated_at DESC"
    with get_conn(db_path) as conn:
        return _rows(conn.execute(q, params))


# ── tweets ──────────────────────────────────────────────────────────────────────
def create_tweet(db_path: str, text: str) -> int:
    with get_conn(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO tweets (text, status, created_at) VALUES (?, 'proposed', ?)",
            (text, _now()),
        )
        return int(cur.lastrowid)


_TWEET_FIELDS = {"text", "status", "scheduled_at", "published_at", "external_id"}


def update_tweet(db_path: str, tweet_id: int, **fields: Any) -> None:
    updates = {k: v for k, v in fields.items() if k in _TWEET_FIELDS}
    if not updates:
        return
    cols = ", ".join(f"{k} = ?" for k in updates)
    with get_conn(db_path) as conn:
        conn.execute(
            f"UPDATE tweets SET {cols} WHERE id = ?", (*updates.values(), tweet_id)
        )


def list_tweets(db_path: str, status: str | None = None) -> list[dict[str, Any]]:
    q = "SELECT * FROM tweets"
    params: list[Any] = []
    if status:
        q += " WHERE status = ?"; params.append(status)
    q += " ORDER BY created_at DESC"
    with get_conn(db_path) as conn:
        return _rows(conn.execute(q, params))


# ── prompt_versions ───────────────────────────────────────────────────────────
def add_prompt_version(db_path: str, name: str, content: str, editor: str | None) -> int:
    with get_conn(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO prompt_versions (name, content, editor, created_at) VALUES (?,?,?,?)",
            (name, content, editor, _now()),
        )
        return int(cur.lastrowid)


def get_latest_prompt(db_path: str, name: str) -> dict[str, Any] | None:
    with get_conn(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM prompt_versions WHERE name = ? ORDER BY created_at DESC LIMIT 1",
            (name,),
        ).fetchone()
        return dict(row) if row else None


def list_prompt_versions(db_path: str, name: str) -> list[dict[str, Any]]:
    with get_conn(db_path) as conn:
        return _rows(
            conn.execute(
                "SELECT * FROM prompt_versions WHERE name = ? ORDER BY created_at DESC",
                (name,),
            )
        )


# ── editor_log ────────────────────────────────────────────────────────────────
def log_message(db_path: str, direction: str, text: str) -> None:
    with get_conn(db_path) as conn:
        conn.execute(
            "INSERT INTO editor_log (direction, text, created_at) VALUES (?,?,?)",
            (direction, text, _now()),
        )
