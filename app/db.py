"""SQLite 数据层（标准库 sqlite3，无第三方依赖）。"""
from __future__ import annotations

import sqlite3
import time
import uuid
from pathlib import Path

from .config import DB_PATH, DEFAULT_SOURCE

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id           TEXT PRIMARY KEY,
    raw_text     TEXT NOT NULL,
    task_text    TEXT NOT NULL,
    source       TEXT DEFAULT '企业微信',
    status       TEXT DEFAULT 'todo',
    remind_at    INTEGER,
    created_at   INTEGER NOT NULL,
    updated_at   INTEGER NOT NULL,
    completed_at INTEGER,
    archived     INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status, archived);
CREATE INDEX IF NOT EXISTS idx_tasks_remind ON tasks(remind_at);
"""


def now_ms() -> int:
    return int(time.time() * 1000)


class DB:
    def __init__(self, path: str | Path = DB_PATH) -> None:
        self.path = Path(path)
        self._connect(self.path)

    def _connect(self, path: Path) -> None:
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # ---------- 数据目录迁移 ----------
    def backup_to(self, path: str | Path) -> None:
        """把当前库完整复制到目标文件（用 sqlite backup API，WAL 下也安全）。"""
        target = sqlite3.connect(str(path))
        try:
            with target:
                self.conn.backup(target)
        finally:
            target.close()

    def reopen(self, path: str | Path) -> None:
        """切换到另一个数据库文件，切换前关闭旧连接。"""
        new_path = Path(path)
        try:
            self.conn.close()
        except Exception:
            pass
        self.path = new_path
        self._connect(new_path)

    # ---------- 写 ----------
    def create(self, raw_text: str, task_text: str | None = None,
               source: str = DEFAULT_SOURCE, remind_at: int | None = None) -> dict | None:
        raw_text = (raw_text or "").strip()
        if not raw_text:
            return None
        if not task_text:
            first = next((l.strip() for l in raw_text.splitlines() if l.strip()), raw_text)
            task_text = first[:200]
        tid = uuid.uuid4().hex
        ts = now_ms()
        with self.conn:
            self.conn.execute(
                "INSERT INTO tasks(id, raw_text, task_text, source, status, remind_at,"
                " created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
                (tid, raw_text, task_text, source or DEFAULT_SOURCE,
                 "todo", remind_at, ts, ts),
            )
        return self.get(tid)

    def update(self, tid: str, **patch) -> None:
        allowed = {"raw_text", "task_text", "source", "status", "remind_at",
                   "completed_at", "archived"}
        fields = {k: v for k, v in patch.items() if k in allowed}
        if not fields:
            return
        fields["updated_at"] = now_ms()
        sets = ", ".join(f"{k} = ?" for k in fields)
        with self.conn:
            self.conn.execute(f"UPDATE tasks SET {sets} WHERE id = ?",
                              (*fields.values(), tid))

    def complete(self, tid: str) -> None:
        ts = now_ms()
        with self.conn:
            self.conn.execute(
                "UPDATE tasks SET status='done', completed_at=?, updated_at=? WHERE id=?",
                (ts, ts, tid))

    def snooze(self, tid: str, minutes: int = 10) -> None:
        ts = now_ms()
        with self.conn:
            self.conn.execute(
                "UPDATE tasks SET remind_at=?, status=CASE WHEN status='done' THEN 'later'"
                " ELSE status END, updated_at=? WHERE id=?",
                (ts + minutes * 60_000, ts, tid))

    def archive(self, tid: str) -> None:
        self.update(tid, archived=1)

    def delete(self, tid: str) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM tasks WHERE id=?", (tid,))

    # ---------- 读 ----------
    def get(self, tid: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
        return dict(row) if row else None

    def list_tasks(self, search: str = "", include_done: bool = True,
                   include_archived: bool = False) -> list[dict]:
        sql = "SELECT * FROM tasks WHERE 1=1"
        args: list = []
        if not include_archived:
            sql += " AND archived = 0"
        if not include_done:
            sql += " AND status != 'done'"
        if search:
            sql += " AND (raw_text LIKE ? OR task_text LIKE ? OR source LIKE ?)"
            like = f"%{search}%"
            args += [like, like, like]
        sql += " ORDER BY (status='done') ASC, created_at DESC"
        return [dict(r) for r in self.conn.execute(sql, args)]

    def open_count(self) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE archived=0 AND status!='done'").fetchone()
        return int(row[0])

    def due_tasks(self, ts: int | None = None) -> list[dict]:
        ts = ts or now_ms()
        rows = self.conn.execute(
            "SELECT * FROM tasks WHERE archived=0 AND status!='done'"
            " AND remind_at IS NOT NULL AND remind_at <= ?", (ts,))
        return [dict(r) for r in rows]
