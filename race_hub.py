"""
Racing & media ops hub — SQLite-backed notes for the team's race cars,
video/data ops, and monitoring context.

Items are grouped by section (fleet | media | monitoring | general) with a
short status flag so the UI can render readiness at a glance. This is for
operational notes, runbooks, and links — live machine metrics still live in
ssh_metrics.py.
"""
from db import _conn, _lock

SECTIONS = ("fleet", "media", "monitoring", "general")
STATUSES = ("ok", "attention", "unknown")

SCHEMA = """
CREATE TABLE IF NOT EXISTS race_hub_items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    section     TEXT    NOT NULL DEFAULT 'general',
    title       TEXT    NOT NULL,
    detail      TEXT    DEFAULT '',
    status      TEXT    DEFAULT 'unknown',
    link_url    TEXT    DEFAULT '',
    sort_order  INTEGER DEFAULT 0,
    created_at  TEXT    DEFAULT (datetime('now')),
    updated_at  TEXT    DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS race_hub_section_sort
    ON race_hub_items(section, sort_order);
"""


def init_schema():
    with _lock, _conn() as c:
        c.executescript(SCHEMA)


def _normalize_section(section: str | None) -> str:
    s = (section or "general").strip().lower()
    return s if s in SECTIONS else "general"


def _normalize_status(status: str | None) -> str:
    s = (status or "unknown").strip().lower()
    return s if s in STATUSES else "unknown"


def list_items(section: str | None = None, query: str = "") -> list[dict]:
    sql = "SELECT id, section, title, detail, status, link_url, sort_order, created_at, updated_at FROM race_hub_items"
    params: list = []
    where: list[str] = []
    if section:
        where.append("section = ?")
        params.append(_normalize_section(section))
    if query:
        where.append("(title LIKE ? OR detail LIKE ?)")
        like = f"%{query}%"
        params.extend([like, like])
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY section ASC, sort_order ASC, created_at ASC"
    with _lock, _conn() as c:
        rows = c.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def get_item(item_id: int) -> dict | None:
    with _lock, _conn() as c:
        row = c.execute(
            "SELECT id, section, title, detail, status, link_url, sort_order, created_at, updated_at "
            "FROM race_hub_items WHERE id = ?",
            (item_id,),
        ).fetchone()
    return dict(row) if row else None


def create_item(
    section: str,
    title: str,
    detail: str = "",
    status: str = "unknown",
    link_url: str = "",
    sort_order: int = 0,
) -> dict:
    title = (title or "").strip()
    if not title:
        raise ValueError("title is required")
    with _lock, _conn() as c:
        cur = c.execute(
            "INSERT INTO race_hub_items (section, title, detail, status, link_url, sort_order) "
            "VALUES (?,?,?,?,?,?)",
            (
                _normalize_section(section),
                title,
                detail or "",
                _normalize_status(status),
                link_url or "",
                int(sort_order or 0),
            ),
        )
        new_id = cur.lastrowid
        row = c.execute(
            "SELECT id, section, title, detail, status, link_url, sort_order, created_at, updated_at "
            "FROM race_hub_items WHERE id = ?",
            (new_id,),
        ).fetchone()
    return dict(row)


_UPDATABLE = {"section", "title", "detail", "status", "link_url", "sort_order"}


def update_item(item_id: int, **fields) -> dict | None:
    clean: dict = {}
    for k, v in fields.items():
        if k not in _UPDATABLE or v is None:
            continue
        if k == "section":
            clean[k] = _normalize_section(v)
        elif k == "status":
            clean[k] = _normalize_status(v)
        elif k == "sort_order":
            clean[k] = int(v)
        elif k == "title":
            t = str(v).strip()
            if not t:
                continue
            clean[k] = t
        else:
            clean[k] = str(v)
    if not clean:
        return get_item(item_id)
    sets = ", ".join(f"{k} = ?" for k in clean) + ", updated_at = datetime('now')"
    params = list(clean.values()) + [item_id]
    with _lock, _conn() as c:
        c.execute(f"UPDATE race_hub_items SET {sets} WHERE id = ?", params)
    return get_item(item_id)


def delete_item(item_id: int) -> bool:
    with _lock, _conn() as c:
        cur = c.execute("DELETE FROM race_hub_items WHERE id = ?", (item_id,))
        return cur.rowcount > 0
