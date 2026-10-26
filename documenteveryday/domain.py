"""The nouns of the pipeline: words, segments, moments, clip plans and captions.

Pure data. Every stage takes these in and hands these out, so each stage can be tested alone.
"""

from dataclasses import dataclass, field
from enum import StrEnum

SENTENCE_ENDING_CHARACTERS = (".", "!", "?", "؟")


class SegmentTag(StrEnum):
    TRAINING = "training"
    FOOD_PREP = "food_prep"
    ARABIC = "arabic"
    TECH_STUDY = "tech_study"
    OTHER = "other"


class GoodClipCriterion(StrEnum):
    EFFORT = "EFFORT"
    RESULT = "RESULT"
    LESSON = "LESSON"


@dataclass(frozen=True)
class TranscribedWord:
    text: str
    start_seconds: float
    end_seconds: float
    probability: float = 1.0

    @property
    def is_arabic(self) -> bool:
        return any("؀" <= character <= "ۿ" for character in self.text)

    @property
    def ends_sentence(self) -> bool:
        return self.text.strip().endswith(SENTENCE_ENDING_CHARACTERS)


@dataclass(frozen=True)
class Transcript:
    source_video_id: int
    words: tuple[TranscribedWord, ...]


@dataclass(frozen=True)
class Segment:
    """A run of words between natural pauses. `index` is unique across the whole batch."""

    index: int
    source_video_id: int
    first_word_index: int
    last_word_index: int
    words: tuple[TranscribedWord, ...]

    @property
    def start_seconds(self) -> float:
        return self.words[0].start_seconds

    @property
    def end_seconds(self) -> float:
        return self.words[-1].end_seconds

    @property
    def text(self) -> str:
        return " ".join(word.text.strip() for word in self.words)


@dataclass(frozen=True)
class SegmentClassification:
    tag: SegmentTag
    reason: str


@dataclass(frozen=True)
class ScoredMoment:
    first_segment_index: int
    last_segment_index: int
    score: int
    criteria: tuple[GoodClipCriterion, ...]
    reason: str
    privacy_concern: str = ""


@dataclass(frozen=True)
class ClipPlan:
    """Where to cut: a word range inside one source video's transcript, plus why it was picked."""

    source_video_id: int
    first_word_index: int
    last_word_index: int
    start_seconds: float
    end_seconds: float
    tag: SegmentTag = SegmentTag.OTHER
    tag_reason: str = ""
    score: int = 0
    criteria: tuple[GoodClipCriterion, ...] = ()
    pick_reason: str = ""
    privacy_concern: str = ""

    @property
    def duration_seconds(self) -> float:
        return self.end_seconds - self.start_seconds


@dataclass(frozen=True)
class ClipCopy:
    hook_line: str
    title: str
    post_caption: str
    hashtags: tuple[str, ...]

    @property
    def clipboard_text(self) -> str:
        return f"{self.post_caption}\n\n{' '.join('#' + hashtag for hashtag in self.hashtags)}".strip()


@dataclass(frozen=True)
class CaptionCue:
    """One on-screen caption. Times are relative to the clip start."""

    start_seconds: float
    end_seconds: float
    text: str
    is_arabic: bool = False
    english_translation: str = ""


@dataclass(frozen=True)
class ClipProblem:
    code: str
    detail: str


@dataclass(frozen=True)
class QaOutcome:
    status: str  # "passed" | "fixed" | "flagged"
    summary: str
    fixes: tuple[str, ...] = field(default_factory=tuple)
