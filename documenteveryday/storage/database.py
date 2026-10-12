"""SQLite file with one short-lived connection per operation, which keeps it safe across threads."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS batches (
    id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL,
    status_detail TEXT NOT NULL DEFAULT '',
    total_cost_dollars REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS source_videos (
    id INTEGER PRIMARY KEY,
    batch_id INTEGER NOT NULL REFERENCES batches(id),
    original_filename TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    owned_by_pipeline INTEGER NOT NULL DEFAULT 1,
    uploaded_at TEXT NOT NULL,
    deleted_at TEXT
);
CREATE TABLE IF NOT EXISTS clips (
    id INTEGER PRIMARY KEY,
    batch_id INTEGER NOT NULL REFERENCES batches(id),
    source_video_id INTEGER NOT NULL REFERENCES source_videos(id),
    start_seconds REAL NOT NULL,
    end_seconds REAL NOT NULL,
    tag TEXT NOT NULL DEFAULT 'other',
    tag_reason TEXT NOT NULL DEFAULT '',
    score INTEGER NOT NULL DEFAULT 0,
    criteria TEXT NOT NULL DEFAULT '[]',
    pick_reason TEXT NOT NULL DEFAULT '',
    hook_line TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    post_caption TEXT NOT NULL DEFAULT '',
    hashtags TEXT NOT NULL DEFAULT '[]',
    qa_status TEXT NOT NULL DEFAULT 'pending',
    qa_summary TEXT NOT NULL DEFAULT '',
    qa_fixes TEXT NOT NULL DEFAULT '[]',
    video_path TEXT NOT NULL DEFAULT '',
    review_status TEXT NOT NULL DEFAULT 'pending',
    reviewed_at TEXT
);
CREATE TABLE IF NOT EXISTS ai_decisions (
    id INTEGER PRIMARY KEY,
    batch_id INTEGER NOT NULL REFERENCES batches(id),
    clip_id INTEGER REFERENCES clips(id),
    purpose TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cost_dollars REAL NOT NULL,
    decision TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def utc_now_text() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Database:
    def __init__(self, database_path: Path):
        self.database_path = database_path
        database_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript(SCHEMA)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def fetch_all(self, query: str, parameters: tuple = ()) -> list[dict]:
        with self.connect() as connection:
            return [dict(row) for row in connection.execute(query, parameters).fetchall()]

    def fetch_one(self, query: str, parameters: tuple = ()) -> dict | None:
        rows = self.fetch_all(query, parameters)
        return rows[0] if rows else None

    def execute(self, query: str, parameters: tuple = ()) -> int:
        """Runs a write and returns the new row id."""
        with self.connect() as connection:
            return connection.execute(query, parameters).lastrowid
