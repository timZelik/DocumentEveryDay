"""The QA agent's hands. Each tool changes the clip, re-renders it, and the checks then run again."""

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from documenteveryday.domain import CaptionCue, ClipPlan
from documenteveryday.qa.clip_checks import ClipUnderReview
from documenteveryday.selection.word_boundary_window import WordRange, cut_points_for_word_range

RenderClip = Callable[[ClipPlan, list[CaptionCue]], Path]
BuildCues = Callable[[ClipPlan], list[CaptionCue]]


class InvalidToolInput(ValueError):
    pass


class ClipWorkbench:
    def __init__(self, clip: ClipUnderReview, render_clip: RenderClip, build_cues: BuildCues):
        self.current = clip
        self.render_clip = render_clip
        self.build_cues = build_cues

    def retrim_clip(self, first_word_index: int, last_word_index: int) -> str:
        word_count = len(self.current.transcript_words)
        if not 0 <= first_word_index <= last_word_index < word_count:
            raise InvalidToolInput(f"Word indices must satisfy 0 <= first <= last < {word_count}.")
        start_seconds, end_seconds = cut_points_for_word_range(
            self.current.transcript_words, WordRange(first_word_index, last_word_index)
        )
        plan = replace(
            self.current.plan, first_word_index=first_word_index, last_word_index=last_word_index,
            start_seconds=start_seconds, end_seconds=end_seconds,
        )  # fmt: skip
        self.rerender(plan, self.build_cues(plan))
        return f"Retrimmed to words {first_word_index}-{last_word_index} ({end_seconds - start_seconds:.1f}s)."

    def rewrite_caption(self, cue_index: int, new_text: str) -> str:
        """For an Arabic caption the new text replaces its English line; the Arabic itself is what I said."""
        if not 0 <= cue_index < len(self.current.cues) or not new_text.strip():
            raise InvalidToolInput(f"cue_index must be 0-{len(self.current.cues) - 1} and new_text non-empty.")
        cue = self.current.cues[cue_index]
        rewritten = replace(cue, english_translation=new_text) if cue.is_arabic else replace(cue, text=new_text)
        cues = [*self.current.cues[:cue_index], rewritten, *self.current.cues[cue_index + 1 :]]
        self.rerender(self.current.plan, cues)
        return f"Caption {cue_index} now reads '{new_text}'."

    def rerender(self, plan: ClipPlan, cues: list[CaptionCue]) -> None:
        video_path = self.render_clip(plan, cues)
        self.current = ClipUnderReview(plan, self.current.transcript_words, tuple(cues), video_path)
