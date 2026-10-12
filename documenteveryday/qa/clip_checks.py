"""Deterministic QA checks. Plain code decides pass/fail; Claude is only called when something fails."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from documenteveryday.captions.caption_cues import displayed_lines
from documenteveryday.domain import CaptionCue, ClipPlan, ClipProblem, TranscribedWord
from documenteveryday.media.black_frame_detector import find_black_intervals
from documenteveryday.media.clip_renderer import VERTICAL_HEIGHT, VERTICAL_WIDTH
from documenteveryday.media.ffmpeg_tools import FfmpegFailed, probe_video_dimensions
from documenteveryday.selection.word_boundary_window import DEFAULT_DURATION_LIMITS

MID_WORD_TOLERANCE_SECONDS = 0.02
MAXIMUM_INTERNAL_PAUSE_SECONDS = 2.5
MAXIMUM_EDGE_SILENCE_SECONDS = 1.2
MAXIMUM_CAPTION_LINE_CHARACTERS = 30


@dataclass(frozen=True)
class ClipUnderReview:
    plan: ClipPlan
    transcript_words: tuple[TranscribedWord, ...]
    cues: tuple[CaptionCue, ...]
    video_path: Path

    @property
    def clip_words(self) -> tuple[TranscribedWord, ...]:
        return self.transcript_words[self.plan.first_word_index : self.plan.last_word_index + 1]


def find_cuts_mid_word(clip: ClipUnderReview) -> list[ClipProblem]:
    return [
        ClipProblem("CUT_MID_WORD", f"The {edge} cut at {cut:.2f}s slices the word '{word.text}'.")
        for edge, cut in (("start", clip.plan.start_seconds), ("end", clip.plan.end_seconds))
        for word in clip.transcript_words
        if word.start_seconds + MID_WORD_TOLERANCE_SECONDS < cut < word.end_seconds - MID_WORD_TOLERANCE_SECONDS
    ]


def find_unfinished_sentence(clip: ClipUnderReview) -> list[ClipProblem]:
    last_word = clip.clip_words[-1]
    if last_word.ends_sentence:
        return []
    return [ClipProblem("ENDS_MID_SENTENCE", f"The clip ends on '{last_word.text}' before the sentence finishes.")]


def find_dead_air(clip: ClipUnderReview) -> list[ClipProblem]:
    words = clip.clip_words
    problems = [
        ClipProblem("DEAD_AIR", f"{later.start_seconds - earlier.end_seconds:.1f}s of silence after '{earlier.text}'.")
        for earlier, later in zip(words, words[1:], strict=False)
        if later.start_seconds - earlier.end_seconds > MAXIMUM_INTERNAL_PAUSE_SECONDS
    ]
    leading_silence = words[0].start_seconds - clip.plan.start_seconds
    trailing_silence = clip.plan.end_seconds - words[-1].end_seconds
    if leading_silence > MAXIMUM_EDGE_SILENCE_SECONDS:
        problems.append(ClipProblem("DEAD_AIR", f"{leading_silence:.1f}s of silence before the first word."))
    if trailing_silence > MAXIMUM_EDGE_SILENCE_SECONDS:
        problems.append(ClipProblem("DEAD_AIR", f"{trailing_silence:.1f}s of silence after the last word."))
    return problems


def find_duration_out_of_range(clip: ClipUnderReview) -> list[ClipProblem]:
    duration = clip.plan.duration_seconds
    limits = DEFAULT_DURATION_LIMITS
    if limits.minimum_seconds - 0.05 <= duration <= limits.maximum_seconds + 0.05:
        return []
    return [ClipProblem("DURATION_OUT_OF_RANGE", f"{duration:.1f}s is outside 15-60 seconds.")]


def find_caption_problems(clip: ClipUnderReview) -> list[ClipProblem]:
    problems = []
    for index, cue in enumerate(clip.cues):
        lines = displayed_lines(cue)
        maximum_lines = 3 if cue.is_arabic else 2
        if any(len(line) > MAXIMUM_CAPTION_LINE_CHARACTERS for line in lines) or len(lines) > maximum_lines:
            problems.append(ClipProblem("CAPTION_OVERFLOW", f"Caption {index} is too long to fit: {' / '.join(lines)}"))
        if cue.is_arabic and not cue.english_translation:
            problems.append(ClipProblem("UNTRANSLATED_ARABIC", f"Caption {index} '{cue.text}' has no English."))
    return problems


def find_framing_problems(clip: ClipUnderReview) -> list[ClipProblem]:
    try:
        return framing_problems_in_render(clip.video_path)
    except FfmpegFailed as error:
        return [ClipProblem("BAD_FRAMING", f"Could not inspect the rendered video: {str(error)[-200:]}")]


def framing_problems_in_render(video_path: Path) -> list[ClipProblem]:
    dimensions = probe_video_dimensions(video_path)
    problems = []
    if (dimensions.width, dimensions.height) != (VERTICAL_WIDTH, VERTICAL_HEIGHT):
        problems.append(ClipProblem("BAD_FRAMING", f"Rendered at {dimensions.width}x{dimensions.height}, not 9:16."))
    problems += [
        ClipProblem("BAD_FRAMING", f"Black frames from {start:.1f}s to {end:.1f}s (camera covered?).")
        for start, end in find_black_intervals(video_path)
    ]
    return problems


CLIP_CHECKS: Sequence[Callable[[ClipUnderReview], list[ClipProblem]]] = (
    find_cuts_mid_word,
    find_unfinished_sentence,
    find_dead_air,
    find_duration_out_of_range,
    find_caption_problems,
    find_framing_problems,
)


def find_clip_problems(clip: ClipUnderReview) -> list[ClipProblem]:
    return [problem for check in CLIP_CHECKS for problem in check(clip)]
