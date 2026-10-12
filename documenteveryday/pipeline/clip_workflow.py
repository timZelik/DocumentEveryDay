"""Produces one selected clip: copy in my voice, translated captions, render, agentic QA, review-card record.

If the batch budget runs out (or Claude fails) mid-clip, the clip still ships with plain fallback copy and
is flagged, so the batch never dies on its last few cents."""

import logging
from dataclasses import dataclass, replace
from pathlib import Path

from documenteveryday.captions.arabic_translator import ArabicCaptionTranslator
from documenteveryday.captions.caption_cues import build_caption_cues
from documenteveryday.copywriting.clip_copywriter import ClaudeClipCopywriter, fallback_copy
from documenteveryday.domain import CaptionCue, ClipCopy, ClipPlan, QaOutcome, Transcript
from documenteveryday.llm.budget_ledger import BatchBudgetExceeded
from documenteveryday.llm.claude_gateway import ClaudeCallFailed
from documenteveryday.production.clip_production import ClipProductionRequest, produce_clip
from documenteveryday.qa.clip_checks import ClipUnderReview
from documenteveryday.qa.clip_workbench import ClipWorkbench
from documenteveryday.qa.qa_agent import ClipQaAgent
from documenteveryday.storage.repositories import Repositories
from documenteveryday.voiceover.voiceover_provider import VoiceoverProvider

logger = logging.getLogger(__name__)

AI_UNAVAILABLE_ERRORS = (BatchBudgetExceeded, ClaudeCallFailed)


@dataclass(frozen=True)
class ClipJob:
    batch_id: int
    plan: ClipPlan
    source_path: Path
    transcript: Transcript
    clips_directory: Path


@dataclass(frozen=True)
class ClipAiToolkit:
    copywriter: ClaudeClipCopywriter
    translator: ArabicCaptionTranslator
    qa_agent: ClipQaAgent


def clip_text(transcript: Transcript, plan: ClipPlan) -> str:
    words = transcript.words[plan.first_word_index : plan.last_word_index + 1]
    return " ".join(word.text for word in words)


def with_notes(outcome: QaOutcome, notes: list[str]) -> QaOutcome:
    """Problems found outside the QA loop (privacy mention, AI unavailable) always flag the clip."""
    if not notes:
        return outcome
    return replace(outcome, status="flagged", summary=" ".join([*notes, outcome.summary]))


class ClipWorkflow:
    def __init__(
        self,
        repositories: Repositories,
        ai: ClipAiToolkit,
        voiceover_provider: VoiceoverProvider,
        video_encoder: str,
    ):
        self.repositories = repositories
        self.ai = ai
        self.voiceover_provider = voiceover_provider
        self.video_encoder = video_encoder

    def run(self, job: ClipJob) -> int:
        clip_id = self.repositories.clips.create(job.batch_id, job.plan)
        notes: list[str] = []
        clip_copy = self.write_copy(job, clip_id, notes)
        workbench = self.first_render(job, clip_id, clip_copy, notes)
        outcome = self.quality_check(workbench, clip_id, notes)
        if job.plan.privacy_concern:
            notes.insert(0, f"Privacy check: {job.plan.privacy_concern}.")
        self.save(clip_id, workbench.current, clip_copy, with_notes(outcome, notes))
        return clip_id

    def write_copy(self, job: ClipJob, clip_id: int, notes: list[str]) -> ClipCopy:
        try:
            return self.ai.copywriter.write(job.plan, clip_text(job.transcript, job.plan), clip_id)
        except AI_UNAVAILABLE_ERRORS as error:
            notes.append(f"Copy is a plain fallback ({type(error).__name__}).")
            return fallback_copy(job.plan, clip_text(job.transcript, job.plan))

    def build_cues(self, job: ClipJob, clip_id: int, plan: ClipPlan, notes: list[str]) -> list[CaptionCue]:
        cues = build_caption_cues(job.transcript.words, plan.start_seconds, plan.end_seconds)
        try:
            return self.ai.translator.translate(cues, clip_text(job.transcript, plan), clip_id)
        except AI_UNAVAILABLE_ERRORS as error:
            notes.append(f"Arabic left untranslated ({type(error).__name__}).")
            return cues

    def render(self, job: ClipJob, clip_id: int, clip_copy: ClipCopy, plan: ClipPlan, cues: list[CaptionCue]) -> Path:
        return produce_clip(
            ClipProductionRequest(
                source_path=job.source_path,
                start_seconds=plan.start_seconds,
                end_seconds=plan.end_seconds,
                cues=cues,
                hook_line=clip_copy.hook_line,
                output_directory=job.clips_directory,
                clip_name=f"clip_{clip_id}",
                video_encoder=self.video_encoder,
                replacement_audio_path=self.voiceover_provider.voiceover_for(plan, clip_copy),
            )
        )

    def first_render(self, job: ClipJob, clip_id: int, clip_copy: ClipCopy, notes: list[str]) -> ClipWorkbench:
        def build_cues_for(plan: ClipPlan) -> list[CaptionCue]:
            return self.build_cues(job, clip_id, plan, notes)

        def render_for(plan: ClipPlan, cues: list[CaptionCue]) -> Path:
            return self.render(job, clip_id, clip_copy, plan, cues)

        cues = build_cues_for(job.plan)
        clip = ClipUnderReview(job.plan, job.transcript.words, tuple(cues), render_for(job.plan, cues))
        return ClipWorkbench(clip, render_for, build_cues_for)

    def quality_check(self, workbench: ClipWorkbench, clip_id: int, notes: list[str]) -> QaOutcome:
        try:
            return self.ai.qa_agent.review(workbench, clip_id)
        except AI_UNAVAILABLE_ERRORS as error:
            return QaOutcome("flagged", f"QA agent could not run ({type(error).__name__}); please check by eye.")

    def save(self, clip_id: int, clip: ClipUnderReview, clip_copy: ClipCopy, outcome: QaOutcome) -> None:
        self.repositories.clips.update(
            clip_id,
            start_seconds=clip.plan.start_seconds,
            end_seconds=clip.plan.end_seconds,
            hook_line=clip_copy.hook_line,
            title=clip_copy.title,
            post_caption=clip_copy.post_caption,
            hashtags=clip_copy.hashtags,
            qa_status=outcome.status,
            qa_summary=outcome.summary,
            qa_fixes=outcome.fixes,
            video_path=str(clip.video_path),
        )
