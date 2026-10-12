"""One evening's footage in, reviewable clips out. Each step is a small method that reads like the flow."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from documenteveryday.classification.segment_classifier import ClaudeSegmentClassifier, SegmentClassifier
from documenteveryday.config import Settings
from documenteveryday.domain import ClipPlan, Segment, SegmentClassification, Transcript
from documenteveryday.llm.budget_ledger import BatchBudgetLedger
from documenteveryday.llm.claude_gateway import ClaudeGateway
from documenteveryday.notifications.notifier import Notifier
from documenteveryday.pipeline.batch_workspace import BatchWorkspace
from documenteveryday.pipeline.clip_workflow import ClipJob, ClipWorkflow
from documenteveryday.segmentation.segmenter import split_transcripts_into_segments
from documenteveryday.selection.clip_selector import select_clip_plans
from documenteveryday.selection.moment_scorer import ClaudeMomentScorer
from documenteveryday.selection.post_selection_stage import KeepSelectionAsIs, PostSelectionStage
from documenteveryday.storage.repositories import Repositories
from documenteveryday.transcript_files import load_transcript, save_transcript
from documenteveryday.transcription.transcriber import Transcriber

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BatchAnalysis:
    transcripts: list[Transcript]
    segments: list[Segment]
    classifications: dict[int, SegmentClassification]
    plans: list[ClipPlan]


class BatchPipeline:
    def __init__(
        self,
        settings: Settings,
        repositories: Repositories,
        transcriber: Transcriber,
        claude_client: Any,
        notifier: Notifier,
        classifier_factory: Callable[[ClaudeGateway], SegmentClassifier] = ClaudeSegmentClassifier,
        post_selection_stage: PostSelectionStage | None = None,
    ):
        self.settings = settings
        self.repositories = repositories
        self.transcriber = transcriber
        self.claude_client = claude_client
        self.notifier = notifier
        self.classifier_factory = classifier_factory
        self.post_selection_stage = post_selection_stage or KeepSelectionAsIs()

    def run(self, batch_id: int) -> None:
        already_spent_dollars = self.repositories.ai_decisions.total_cost_for_batch(batch_id)
        ledger = BatchBudgetLedger(self.settings.batch_budget_dollars, already_spent_dollars)
        gateway = ClaudeGateway(
            self.claude_client, self.settings.claude_model, batch_id, ledger, self.repositories.ai_decisions.record
        )
        workspace = BatchWorkspace(self.settings.data_directory, batch_id)
        self.repositories.clips.delete_for_batch(batch_id)  # a re-run after a crash starts clean
        try:
            clip_count = self.process(batch_id, workspace, gateway)
        except Exception as error:
            logger.exception("Batch %s failed", batch_id)
            self.finish(batch_id, ledger, "failed", f"{type(error).__name__}: {error}")
            self.notifier.batch_failed(batch_id, str(error))
            return
        self.finish(batch_id, ledger, "ready", f"{clip_count} clips ready")
        self.notifier.batch_ready(batch_id, clip_count, ledger.spent_dollars)

    def process(self, batch_id: int, workspace: BatchWorkspace, gateway: ClaudeGateway) -> int:
        source_paths = self.source_paths_by_video(batch_id)
        analysis = self.analyse(batch_id, workspace, gateway, source_paths)
        transcripts_by_video = {transcript.source_video_id: transcript for transcript in analysis.transcripts}
        workflow = ClipWorkflow(self.repositories, self.settings.video_encoder)
        for position, plan in enumerate(analysis.plans, start=1):
            self.report(batch_id, f"Producing clip {position} of {len(analysis.plans)}")
            workflow.run(
                ClipJob(
                    batch_id, plan, source_paths[plan.source_video_id],
                    transcripts_by_video[plan.source_video_id], workspace.clips_directory,
                )
            )  # fmt: skip
        return len(analysis.plans)

    def analyse(
        self, batch_id: int, workspace: BatchWorkspace, gateway: ClaudeGateway, source_paths: dict[int, Path]
    ) -> BatchAnalysis:
        transcripts = self.transcribe_all(batch_id, workspace, source_paths)
        segments = split_transcripts_into_segments(transcripts)
        self.report(batch_id, f"Tagging {len(segments)} segments")
        classifications = self.classifier_factory(gateway).classify(segments)
        self.report(batch_id, "Scoring moments against your rule")
        rule_text = self.settings.rule_path.read_text()
        moments = ClaudeMomentScorer(gateway, rule_text).score(segments, classifications)
        plans = select_clip_plans(
            moments, segments, transcripts, classifications,
            self.settings.maximum_clips_per_batch, self.settings.minimum_clip_score,
        )  # fmt: skip
        return BatchAnalysis(transcripts, segments, classifications, self.post_selection_stage.process(plans))

    def transcribe_all(
        self, batch_id: int, workspace: BatchWorkspace, source_paths: dict[int, Path]
    ) -> list[Transcript]:
        transcripts = []
        for position, (source_video_id, source_path) in enumerate(source_paths.items(), start=1):
            self.report(batch_id, f"Transcribing video {position} of {len(source_paths)}")
            transcripts.append(self.cached_transcript(workspace, source_video_id, source_path))
        return transcripts

    def cached_transcript(self, workspace: BatchWorkspace, source_video_id: int, source_path: Path) -> Transcript:
        transcript_path = workspace.transcript_path(source_video_id)
        if transcript_path.exists():
            return load_transcript(transcript_path)
        transcript = self.transcriber.transcribe(source_path, source_video_id)
        save_transcript(transcript, transcript_path)
        return transcript

    def source_paths_by_video(self, batch_id: int) -> dict[int, Path]:
        source_videos = self.repositories.source_videos.for_batch(batch_id)
        if not source_videos:
            raise ValueError("This batch has no footage.")
        return {video["id"]: Path(video["stored_path"]) for video in source_videos}

    def report(self, batch_id: int, status_detail: str) -> None:
        logger.info("Batch %s: %s", batch_id, status_detail)
        self.repositories.batches.set_status(batch_id, "processing", status_detail)

    def finish(self, batch_id: int, ledger: BatchBudgetLedger, status: str, status_detail: str) -> None:
        self.repositories.batches.set_total_cost(batch_id, ledger.spent_dollars)
        self.repositories.batches.set_status(batch_id, status, status_detail)
