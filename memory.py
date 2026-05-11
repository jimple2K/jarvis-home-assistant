"""
Supabase-backed long-term memory for Jarvis.
Stores conversation summaries, facts, and preferences.
Retrieves relevant context before each response.
"""
import os
import json
import datetime
from dotenv import load_dotenv

load_dotenv()

_client = None


def _get_client():
    global _client
    if _client:
        return _client
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_ANON_KEY", "")
    if not url or not key:
        return None
    try:
        from supabase import create_client
        _client = create_client(url, key)
        return _client
    except Exception as e:
        print(f"Supabase init error: {e}")
        return None


def is_connected() -> bool:
    return _get_client() is not None


# ── Schema (run once via /memory/init endpoint) ───────────────────────────────

SCHEMA_SQL = """
create table if not exists memories (
    id          bigserial primary key,
    type        text not null default 'fact',
    content     text not null,
    tags        text[] default '{}',
    importance  int  default 1,
    created_at  timestamptz default now(),
    updated_at  timestamptz default now()
);

create table if not exists conversations (
    id          bigserial primary key,
    user_msg    text,
    jarvis_reply text,
    tools_used  text[] default '{}',
    created_at  timestamptz default now()
);

create index if not exists memories_type_idx on memories(type);
create index if not exists memories_created_idx on memories(created_at desc);
"""


# ── Core operations ───────────────────────────────────────────────────────────

def store_memory(content: str, type: str = "fact", tags: list = None, importance: int = 1) -> str:
    sb = _get_client()
    if not sb:
        return "Supabase not configured."
    try:
        sb.table("memories").insert({
            "content":    content,
            "type":       type,
            "tags":       tags or [],
            "importance": importance,
        }).execute()
        return f"Stored memory: {content[:80]}"
    except Exception as e:
        return f"Error storing memory: {e}"


def search_memories(query: str, limit: int = 6) -> str:
    sb = _get_client()
    if not sb:
        return ""
    try:
        # Simple keyword search across content
        results = (
            sb.table("memories")
            .select("content, type, tags, importance, created_at")
            .ilike("content", f"%{query}%")
            .order("importance", desc=True)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        rows = results.data or []
        if not rows:
            return ""
        lines = [f"[{r['type']}] {r['content']}" for r in rows]
        return "Relevant memories:\n" + "\n".join(lines)
    except Exception as e:
        return ""


def get_recent_memories(limit: int = 8) -> str:
    sb = _get_client()
    if not sb:
        return ""
    try:
        results = (
            sb.table("memories")
            .select("content, type, importance, created_at")
            .order("importance", desc=True)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        rows = results.data or []
        if not rows:
            return ""
        lines = [f"[{r['type']}] {r['content']}" for r in rows]
        return "What I remember:\n" + "\n".join(lines)
    except Exception as e:
        return ""


def log_conversation(user_msg: str, jarvis_reply: str, tools_used: list = None):
    sb = _get_client()
    if not sb:
        return
    try:
        sb.table("conversations").insert({
            "user_msg":     user_msg,
            "jarvis_reply": jarvis_reply,
            "tools_used":   tools_used or [],
        }).execute()
    except Exception:
        pass


def delete_memory(memory_id: int) -> str:
    sb = _get_client()
    if not sb:
        return "Supabase not configured."
    try:
        sb.table("memories").delete().eq("id", memory_id).execute()
        return f"Deleted memory {memory_id}"
    except Exception as e:
        return f"Error: {e}"


def list_all_memories(limit: int = 20) -> str:
    sb = _get_client()
    if not sb:
        return "Supabase not configured."
    try:
        results = (
            sb.table("memories")
            .select("id, type, content, importance, created_at")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        rows = results.data or []
        if not rows:
            return "No memories stored yet."
        lines = [f"ID {r['id']} [{r['type']}] (importance {r['importance']}): {r['content']}" for r in rows]
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"
