"""
Local SQLite database — no account, no internet required.
Stores memories, conversations, topics, and concepts.
"""
import sqlite3
import json
import os
import threading
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), "jarvis.db")
_lock   = threading.Lock()


def _conn():
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


def init():
    with _lock, _conn() as c:
        c.executescript("""
            PRAGMA foreign_keys = ON;""")
    with _lock, _conn() as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS memories (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                type        TEXT    DEFAULT 'fact',
                content     TEXT    NOT NULL,
                importance  INTEGER DEFAULT 1,
                created_at  TEXT    DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS conversations (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_msg     TEXT,
                jarvis_reply TEXT,
                tools_used   TEXT DEFAULT '[]',
                created_at   TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS topics (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT NOT NULL,
                description TEXT DEFAULT '',
                active      INTEGER DEFAULT 0,
                pinned      INTEGER DEFAULT 0,
                created_at  TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS concepts (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                text        TEXT NOT NULL,
                category    TEXT DEFAULT 'info',
                expires_at  TEXT,
                created_at  TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS mem_importance ON memories(importance DESC);
            CREATE INDEX IF NOT EXISTS mem_created    ON memories(created_at DESC);
            CREATE INDEX IF NOT EXISTS topics_active  ON topics(active DESC);
        """)
    # SSH schema lives in ssh_metrics to keep it colocated
    try:
        import ssh_metrics
        ssh_metrics.init_schema()
    except Exception:
        pass


# ── Memories ──────────────────────────────────────────────────────────────────

def store_memory(content: str, type: str = "fact", importance: int = 1) -> str:
    with _lock, _conn() as c:
        c.execute(
            "INSERT INTO memories (type, content, importance) VALUES (?,?,?)",
            (type, content, importance)
        )
    return f"Stored: {content[:80]}"


def search_memories(query: str, limit: int = 6) -> str:
    with _lock, _conn() as c:
        rows = c.execute(
            """SELECT type, content FROM memories
               WHERE content LIKE ?
               ORDER BY importance DESC, created_at DESC LIMIT ?""",
            (f"%{query}%", limit)
        ).fetchall()
    if not rows:
        return ""
    return "Relevant memories:\n" + "\n".join(f"[{r['type']}] {r['content']}" for r in rows)


def list_all_memories(limit: int = 20) -> str:
    with _lock, _conn() as c:
        rows = c.execute(
            "SELECT id, type, content, importance FROM memories ORDER BY created_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
    if not rows:
        return "No memories yet."
    return "\n".join(f"ID {r['id']} [{r['type']}] ★{r['importance']}: {r['content']}" for r in rows)


def delete_memory(memory_id: int) -> str:
    with _lock, _conn() as c:
        c.execute("DELETE FROM memories WHERE id=?", (memory_id,))
    return f"Deleted memory {memory_id}"


# ── Conversations ─────────────────────────────────────────────────────────────

def log_conversation(user_msg: str, jarvis_reply: str, tools_used: list = None):
    with _lock, _conn() as c:
        c.execute(
            "INSERT INTO conversations (user_msg, jarvis_reply, tools_used) VALUES (?,?,?)",
            (user_msg, jarvis_reply, json.dumps(tools_used or []))
        )


# ── Topics ────────────────────────────────────────────────────────────────────

def add_topic(title: str, description: str = "") -> dict:
    with _lock, _conn() as c:
        cur = c.execute(
            "INSERT INTO topics (title, description) VALUES (?,?)",
            (title, description)
        )
        return {"id": cur.lastrowid, "title": title, "description": description, "active": 0}


def remove_topic(topic_id: int) -> str:
    with _lock, _conn() as c:
        c.execute("DELETE FROM topics WHERE id=?", (topic_id,))
    return f"Removed topic {topic_id}"


def set_active_topic(topic_id: int) -> str:
    with _lock, _conn() as c:
        c.execute("UPDATE topics SET active=0")
        if topic_id:
            c.execute("UPDATE topics SET active=1 WHERE id=?", (topic_id,))
    return f"Topic {topic_id} is now active"


def get_topics() -> list:
    with _lock, _conn() as c:
        rows = c.execute(
            "SELECT id, title, description, active, pinned FROM topics ORDER BY pinned DESC, created_at ASC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_active_topic() -> dict | None:
    with _lock, _conn() as c:
        row = c.execute("SELECT id, title, description FROM topics WHERE active=1").fetchone()
    return dict(row) if row else None


def pin_topic(topic_id: int, pinned: bool) -> str:
    with _lock, _conn() as c:
        c.execute("UPDATE topics SET pinned=? WHERE id=?", (1 if pinned else 0, topic_id))
    return f"Topic {topic_id} {'pinned' if pinned else 'unpinned'}"


# ── Concepts ──────────────────────────────────────────────────────────────────

def add_concept(text: str, category: str = "info", ttl_minutes: int = 60, key: str = "") -> str:
    expires = (datetime.utcnow() + timedelta(minutes=ttl_minutes)).strftime("%Y-%m-%d %H:%M:%S")
    with _lock, _conn() as c:
        if key:
            # Replace any existing concept for this key+category regardless of changing values
            c.execute("DELETE FROM concepts WHERE text LIKE ? AND category=?",
                      (f"%{key}%", category))
        else:
            c.execute("DELETE FROM concepts WHERE text=?", (text,))
        c.execute(
            "INSERT INTO concepts (text, category, expires_at) VALUES (?,?,?)",
            (text, category, expires)
        )
    return f"Added concept: {text}"


def get_concepts() -> list:
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    with _lock, _conn() as c:
        # Clean expired
        c.execute("DELETE FROM concepts WHERE expires_at IS NOT NULL AND expires_at < ?", (now,))
        rows = c.execute(
            "SELECT id, text, category FROM concepts ORDER BY created_at DESC LIMIT 20"
        ).fetchall()
    return [dict(r) for r in rows]


def remove_concept(concept_id: int) -> str:
    with _lock, _conn() as c:
        c.execute("DELETE FROM concepts WHERE id=?", (concept_id,))
    return f"Removed concept {concept_id}"
