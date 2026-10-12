"""Fills the review page with evenly spaced plain cuts of one video, to test the page before any AI runs."""

from pathlib import Path

from documenteveryday.domain import ClipPlan
from documenteveryday.media.ffmpeg_tools import probe_duration_seconds
from documenteveryday.production.clip_production import ClipProductionRequest, produce_clip
from documenteveryday.storage.repositories import Repositories

SEEDED_CLIP_SECONDS = 20.0


def evenly_spaced_windows(video_duration: float, clip_count: int) -> list[tuple[float, float]]:
    spacing = video_duration / clip_count
    return [
        (index * spacing, min(index * spacing + SEEDED_CLIP_SECONDS, video_duration))
        for index in range(clip_count)
        if index * spacing + 1.0 < video_duration
    ]


def seed_review_batch(
    repositories: Repositories, video_path: Path, clips_directory: Path, clip_count: int, video_encoder: str
) -> int:
    batch_id = repositories.batches.create()
    source_video_id = repositories.source_videos.add(
        batch_id, video_path.name, str(video_path.resolve()), owned_by_pipeline=False
    )
    windows = evenly_spaced_windows(probe_duration_seconds(video_path), clip_count)
    for start_seconds, end_seconds in windows:
        plan = ClipPlan(source_video_id, 0, 0, start_seconds, end_seconds, pick_reason="Seeded test cut; no AI ran.")
        clip_id = repositories.clips.create(batch_id, plan)
        rendered_path = produce_clip(
            ClipProductionRequest(
                video_path, start_seconds, end_seconds, [], "", clips_directory / str(batch_id),
                f"clip_{clip_id}", video_encoder,
            )
        )  # fmt: skip
        repositories.clips.update(
            clip_id, video_path=str(rendered_path), title=f"Seeded cut at {start_seconds:.0f}s",
            post_caption="Seeded caption for testing the clipboard.", hashtags=("documenteveryday",),
            qa_status="passed", qa_summary="Not checked (seeded).",
        )  # fmt: skip
    repositories.batches.set_status(batch_id, "ready")
    return batch_id
