"""Produces one selected clip: captions, render, and the review-card record."""

import logging
from dataclasses import dataclass
from pathlib import Path

from documenteveryday.captions.caption_cues import build_caption_cues
from documenteveryday.domain import ClipPlan, Transcript
from documenteveryday.production.clip_production import ClipProductionRequest, produce_clip
from documenteveryday.storage.repositories import Repositories

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ClipJob:
    batch_id: int
    plan: ClipPlan
    source_path: Path
    transcript: Transcript
    clips_directory: Path


class ClipWorkflow:
    def __init__(self, repositories: Repositories, video_encoder: str):
        self.repositories = repositories
        self.video_encoder = video_encoder

    def run(self, job: ClipJob) -> int:
        clip_id = self.repositories.clips.create(job.batch_id, job.plan)
        cues = build_caption_cues(job.transcript.words, job.plan.start_seconds, job.plan.end_seconds)
        video_path = produce_clip(
            ClipProductionRequest(
                job.source_path, job.plan.start_seconds, job.plan.end_seconds, cues, "",
                job.clips_directory, f"clip_{clip_id}", self.video_encoder,
            )
        )  # fmt: skip
        self.repositories.clips.update(clip_id, video_path=str(video_path), qa_status="not_checked")
        return clip_id
