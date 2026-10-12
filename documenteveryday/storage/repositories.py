"""One small repository per table. Lists are stored as JSON text and decoded on the way out."""

import json
from dataclasses import dataclass

from documenteveryday.domain import ClipPlan
from documenteveryday.storage.database import Database, utc_now_text

CLIP_JSON_COLUMNS = ("criteria", "hashtags", "qa_fixes")
UPDATABLE_CLIP_COLUMNS = {
    "start_seconds", "end_seconds", "hook_line", "title", "post_caption", "hashtags",
    "qa_status", "qa_summary", "qa_fixes", "video_path", "review_status", "reviewed_at", "voice_note_path",
}  # fmt: skip


def encode_json_columns(fields: dict) -> dict:
    return {
        column: json.dumps(list(value)) if column in CLIP_JSON_COLUMNS else value for column, value in fields.items()
    }


def decode_json_columns(row: dict) -> dict:
    return {column: json.loads(value) if column in CLIP_JSON_COLUMNS else value for column, value in row.items()}


class BatchRepository:
    def __init__(self, database: Database):
        self.database = database

    def create(self) -> int:
        return self.database.execute(
            "INSERT INTO batches (created_at, status) VALUES (?, 'uploading')", (utc_now_text(),)
        )

    def get(self, batch_id: int) -> dict | None:
        return self.database.fetch_one("SELECT * FROM batches WHERE id = ?", (batch_id,))

    def latest(self) -> dict | None:
        return self.database.fetch_one("SELECT * FROM batches ORDER BY id DESC LIMIT 1")

    def with_status(self, *statuses: str) -> list[dict]:
        placeholders = ",".join("?" * len(statuses))
        return self.database.fetch_all(f"SELECT * FROM batches WHERE status IN ({placeholders})", statuses)

    def set_status(self, batch_id: int, status: str, status_detail: str = "") -> None:
        self.database.execute(
            "UPDATE batches SET status = ?, status_detail = ? WHERE id = ?", (status, status_detail, batch_id)
        )

    def set_total_cost(self, batch_id: int, total_cost_dollars: float) -> None:
        self.database.execute("UPDATE batches SET total_cost_dollars = ? WHERE id = ?", (total_cost_dollars, batch_id))


class SourceVideoRepository:
    def __init__(self, database: Database):
        self.database = database

    def add(self, batch_id: int, original_filename: str, stored_path: str, owned_by_pipeline: bool = True) -> int:
        return self.database.execute(
            "INSERT INTO source_videos (batch_id, original_filename, stored_path, owned_by_pipeline, uploaded_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (batch_id, original_filename, stored_path, int(owned_by_pipeline), utc_now_text()),
        )

    def for_batch(self, batch_id: int) -> list[dict]:
        return self.database.fetch_all(
            "SELECT * FROM source_videos WHERE batch_id = ? AND deleted_at IS NULL ORDER BY id", (batch_id,)
        )

    def owned_uploaded_before(self, cutoff_text: str) -> list[dict]:
        return self.database.fetch_all(
            "SELECT * FROM source_videos WHERE owned_by_pipeline = 1 AND deleted_at IS NULL AND uploaded_at < ?",
            (cutoff_text,),
        )

    def mark_deleted(self, source_video_id: int) -> None:
        self.database.execute("UPDATE source_videos SET deleted_at = ? WHERE id = ?", (utc_now_text(), source_video_id))


class ClipRepository:
    def __init__(self, database: Database):
        self.database = database

    def create(self, batch_id: int, plan: ClipPlan) -> int:
        return self.database.execute(
            "INSERT INTO clips (batch_id, source_video_id, start_seconds, end_seconds, tag, tag_reason, score,"
            " criteria, pick_reason) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                batch_id, plan.source_video_id, plan.start_seconds, plan.end_seconds, plan.tag.value,
                plan.tag_reason, plan.score, json.dumps([criterion.value for criterion in plan.criteria]),
                plan.pick_reason,
            ),
        )  # fmt: skip

    def update(self, clip_id: int, **fields) -> None:
        unknown_columns = set(fields) - UPDATABLE_CLIP_COLUMNS
        if unknown_columns:
            raise ValueError(f"Not updatable: {sorted(unknown_columns)}")
        encoded_fields = encode_json_columns(fields)
        assignments = ", ".join(f"{column} = ?" for column in encoded_fields)
        self.database.execute(f"UPDATE clips SET {assignments} WHERE id = ?", (*encoded_fields.values(), clip_id))

    def get(self, clip_id: int) -> dict | None:
        row = self.database.fetch_one("SELECT * FROM clips WHERE id = ?", (clip_id,))
        return decode_json_columns(row) if row else None

    def for_batch(self, batch_id: int) -> list[dict]:
        rows = self.database.fetch_all("SELECT * FROM clips WHERE batch_id = ? ORDER BY score DESC, id", (batch_id,))
        return [decode_json_columns(row) for row in rows]

    def delete_for_batch(self, batch_id: int) -> None:
        """AI decisions are kept: money spent on an interrupted run still counts toward the batch."""
        self.database.execute("DELETE FROM clips WHERE batch_id = ?", (batch_id,))


@dataclass(frozen=True)
class AiDecision:
    batch_id: int
    clip_id: int | None
    purpose: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_dollars: float
    decision: dict


class AiDecisionRepository:
    def __init__(self, database: Database):
        self.database = database

    def record(self, ai_decision: AiDecision) -> None:
        self.database.execute(
            "INSERT INTO ai_decisions (batch_id, clip_id, purpose, model, input_tokens, output_tokens,"
            " cost_dollars, decision, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                ai_decision.batch_id, ai_decision.clip_id, ai_decision.purpose, ai_decision.model,
                ai_decision.input_tokens, ai_decision.output_tokens, ai_decision.cost_dollars,
                json.dumps(ai_decision.decision, ensure_ascii=False), utc_now_text(),
            ),
        )  # fmt: skip

    def for_batch(self, batch_id: int) -> list[dict]:
        rows = self.database.fetch_all("SELECT * FROM ai_decisions WHERE batch_id = ? ORDER BY id", (batch_id,))
        return [{**row, "decision": json.loads(row["decision"])} for row in rows]

    def total_cost_for_batch(self, batch_id: int) -> float:
        row = self.database.fetch_one(
            "SELECT COALESCE(SUM(cost_dollars), 0) AS total FROM ai_decisions WHERE batch_id = ?", (batch_id,)
        )
        return row["total"]


@dataclass(frozen=True)
class Repositories:
    batches: BatchRepository
    source_videos: SourceVideoRepository
    clips: ClipRepository
    ai_decisions: AiDecisionRepository

    @classmethod
    def for_database(cls, database: Database) -> "Repositories":
        return cls(
            BatchRepository(database),
            SourceVideoRepository(database),
            ClipRepository(database),
            AiDecisionRepository(database),
        )
