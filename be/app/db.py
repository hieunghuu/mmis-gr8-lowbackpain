from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  status TEXT NOT NULL CHECK (status IN ('pending','running','done','failed')),
  original_filename TEXT NOT NULL,
  size_bytes INTEGER NOT NULL,
  input_path TEXT NOT NULL,
  output_path TEXT,
  opt_iso INTEGER NOT NULL DEFAULT 0,
  opt_step1 INTEGER NOT NULL DEFAULT 0,
  labels_present TEXT,
  analysis TEXT,
  error_code TEXT,
  error_message TEXT,
  log_tail TEXT,
  created_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_status_created ON jobs (status, created_at);
"""


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        con = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")
        con.execute("PRAGMA busy_timeout = 10000")
        try:
            yield con
        finally:
            con.close()

    def initialize(self) -> None:
        with self.connect() as con:
            con.execute("PRAGMA journal_mode = WAL")
            con.executescript(SCHEMA)

    def insert(self, values: dict[str, Any]) -> None:
        keys = list(values)
        with self.connect() as con:
            con.execute(
                f"INSERT INTO jobs ({','.join(keys)}) VALUES ({','.join('?' for _ in keys)})",
                [values[k] for k in keys],
            )

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self.connect() as con:
            row = con.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None

    def counts(self) -> dict[str, int]:
        with self.connect() as con:
            rows = con.execute(
                "SELECT status, COUNT(*) n FROM jobs WHERE status IN ('pending','running') GROUP BY status"
            ).fetchall()
        out = {"pending": 0, "running": 0}
        out.update({r["status"]: r["n"] for r in rows})
        return out

    def queue_position(self, row: dict[str, Any]) -> int | None:
        if row["status"] != "pending":
            return None
        with self.connect() as con:
            n = con.execute(
                "SELECT COUNT(*) FROM jobs WHERE status='pending' AND (created_at < ? OR (created_at = ? AND id < ?))",
                (row["created_at"], row["created_at"], row["id"]),
            ).fetchone()[0]
        return int(n) + 1

    def list(self, status: str | None, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
        where, args = (" WHERE status = ?", [status]) if status else ("", [])
        with self.connect() as con:
            total = con.execute("SELECT COUNT(*) FROM jobs" + where, args).fetchone()[0]
            rows = con.execute(
                "SELECT * FROM jobs" + where + " ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
                [*args, limit, offset],
            ).fetchall()
        return [dict(r) for r in rows], int(total)

    def recover_running(self, now: str) -> int:
        with self.connect() as con:
            cur = con.execute(
                "UPDATE jobs SET status='failed', finished_at=?, error_code='WORKER_INTERRUPTED', "
                "error_message='Máy chủ khởi động lại khi job đang chạy' WHERE status='running'",
                (now,),
            )
        return cur.rowcount

    def claim_next(self, now: str) -> dict[str, Any] | None:
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT id FROM jobs WHERE status='pending' ORDER BY created_at,id LIMIT 1").fetchone()
            if not row:
                con.execute("COMMIT")
                return None
            cur = con.execute(
                "UPDATE jobs SET status='running', started_at=? WHERE id=? AND status='pending'",
                (now, row["id"]),
            )
            con.execute("COMMIT")
        return self.get(row["id"]) if cur.rowcount else None

    def complete(self, job_id: str, *, output_path: str, labels: list[int], analysis: dict | None,
                 finished_at: str) -> None:
        with self.connect() as con:
            con.execute(
                "UPDATE jobs SET status='done', output_path=?, labels_present=?, analysis=?, finished_at=?, "
                "error_code=NULL,error_message=NULL,log_tail=NULL WHERE id=? AND status='running'",
                (output_path, json.dumps(labels), json.dumps(analysis, ensure_ascii=False, allow_nan=False)
                 if analysis is not None else None, finished_at, job_id),
            )

    def fail(self, job_id: str, *, code: str, message: str, finished_at: str,
             log_tail: str | None = None) -> None:
        with self.connect() as con:
            con.execute(
                "UPDATE jobs SET status='failed', finished_at=?, error_code=?, error_message=?, log_tail=? "
                "WHERE id=? AND status IN ('pending','running')",
                (finished_at, code, message, log_tail, job_id),
            )

    def delete_if_not_running(self, job_id: str) -> str:
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT status FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not row:
                con.execute("ROLLBACK")
                return "missing"
            if row["status"] == "running":
                con.execute("ROLLBACK")
                return "running"
            con.execute("DELETE FROM jobs WHERE id=?", (job_id,))
            con.execute("COMMIT")
        return "deleted"
