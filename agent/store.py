"""Local SQLite store for drafts and the publishing log (data/agent.db on the USB drive)."""

from __future__ import annotations

import contextlib
import sqlite3
import threading
import time
from pathlib import Path

from . import config

STATUSES = ("draft", "approved", "published", "failed", "rejected")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS drafts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  platform TEXT NOT NULL,
  text TEXT NOT NULL,
  topic TEXT DEFAULT '',
  status TEXT NOT NULL DEFAULT 'draft',
  scheduled_for TEXT DEFAULT '',
  sources TEXT DEFAULT '',
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL,
  published_at REAL,
  result TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  at REAL NOT NULL,
  draft_id INTEGER,
  action TEXT NOT NULL,
  detail TEXT DEFAULT ''
);
"""


class Store:
    def __init__(self, path: Path | None = None):
        self.path = Path(path or config.DATA_DIR / "agent.db")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._conn() as c:
            c.executescript(_SCHEMA)

    @contextlib.contextmanager
    def _conn(self):
        """Open, commit, and always close: open handles lock the file on Windows and USB drives."""
        c = sqlite3.connect(self.path, timeout=30)
        c.row_factory = sqlite3.Row
        try:
            with c:
                yield c
        finally:
            c.close()

    def add_draft(self, platform: str, text: str, topic: str = "", scheduled_for: str = "", sources: str = "") -> dict:
        now = time.time()
        with self._lock, self._conn() as c:
            cur = c.execute(
                "INSERT INTO drafts(platform,text,topic,status,scheduled_for,sources,created_at,updated_at)"
                " VALUES(?,?,?,?,?,?,?,?)",
                (platform, text, topic, "draft", scheduled_for, sources, now, now),
            )
            draft_id = cur.lastrowid
        self.log(draft_id, "created", platform)
        return self.get(draft_id)

    def get(self, draft_id: int) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM drafts WHERE id=?", (draft_id,)).fetchone()
        return dict(row) if row else None

    def list(self, status: str | None = None, limit: int = 200) -> list[dict]:
        q, args = "SELECT * FROM drafts", []
        if status:
            q += " WHERE status=?"
            args.append(status)
        q += " ORDER BY COALESCE(NULLIF(scheduled_for,''),'9999'), id DESC LIMIT ?"
        args.append(limit)
        with self._conn() as c:
            return [dict(r) for r in c.execute(q, args).fetchall()]

    def update(self, draft_id: int, **fields) -> dict:
        allowed = {"text", "status", "scheduled_for", "platform", "topic", "result", "published_at"}
        bad = set(fields) - allowed
        if bad:
            raise ValueError(f"cannot update fields: {sorted(bad)}")
        if "status" in fields and fields["status"] not in STATUSES:
            raise ValueError(f"status must be one of {STATUSES}")
        if not fields:
            return self.get(draft_id)
        fields["updated_at"] = time.time()
        cols = ", ".join(f"{k}=?" for k in fields)
        with self._lock, self._conn() as c:
            c.execute(f"UPDATE drafts SET {cols} WHERE id=?", (*fields.values(), draft_id))
        if "status" in fields:
            self.log(draft_id, "status", fields["status"])
        return self.get(draft_id)

    def delete(self, draft_id: int) -> None:
        with self._lock, self._conn() as c:
            c.execute("DELETE FROM drafts WHERE id=?", (draft_id,))
        self.log(draft_id, "deleted")

    def log(self, draft_id: int | None, action: str, detail: str = "") -> None:
        with self._lock, self._conn() as c:
            c.execute("INSERT INTO log(at,draft_id,action,detail) VALUES(?,?,?,?)", (time.time(), draft_id, action, detail[:2000]))

    def history(self, limit: int = 100) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()]
