"""Shapes one batch, its clips and every AI decision into the JSON the review page renders."""

from collections import defaultdict

from documenteveryday.domain import ClipCopy
from documenteveryday.storage.repositories import Repositories

PUBLIC_CLIP_FIELDS = (
    "id", "tag", "tag_reason", "score", "criteria", "pick_reason", "hook_line", "title", "post_caption",
    "hashtags", "qa_status", "qa_summary", "qa_fixes", "review_status", "start_seconds", "end_seconds",
)  # fmt: skip


def group_decisions_by_clip(decisions: list[dict]) -> dict[int | None, list[dict]]:
    decisions_by_clip: dict[int | None, list[dict]] = defaultdict(list)
    for decision in decisions:
        decisions_by_clip[decision["clip_id"]].append(decision)
    return decisions_by_clip


def public_clip(clip: dict, clip_decisions: list[dict]) -> dict:
    clip_copy = ClipCopy(clip["hook_line"], clip["title"], clip["post_caption"], tuple(clip["hashtags"]))
    return {
        **{field: clip[field] for field in PUBLIC_CLIP_FIELDS},
        "is_playable": bool(clip["video_path"]),
        "video_url": f"/media/clips/{clip['id']}",
        "voice_note_url": f"/media/voice-notes/{clip['id']}" if clip["voice_note_path"] else "",
        "clipboard_text": clip_copy.clipboard_text,
        "ai_decisions": clip_decisions,
        "ai_cost_dollars": sum(decision["cost_dollars"] for decision in clip_decisions),
    }


def build_review_payload(repositories: Repositories, batch: dict) -> dict:
    decisions_by_clip = group_decisions_by_clip(repositories.ai_decisions.for_batch(batch["id"]))
    clips = [
        public_clip(clip, decisions_by_clip.get(clip["id"], [])) for clip in repositories.clips.for_batch(batch["id"])
    ]
    return {
        "batch": batch,
        "clips": clips,
        "batch_decisions": decisions_by_clip.get(None, []),
        "total_cost_dollars": batch["total_cost_dollars"],
    }
