"""Turns word ranges into cut points that never slice a word, and fits them to the 15-60 second window."""

from collections.abc import Sequence
from dataclasses import dataclass

from documenteveryday.domain import TranscribedWord

LEAD_PADDING_SECONDS = 0.15
TAIL_PADDING_SECONDS = 0.30


@dataclass(frozen=True)
class WordRange:
    first_word_index: int
    last_word_index: int


@dataclass(frozen=True)
class DurationLimits:
    minimum_seconds: float = 15.0
    maximum_seconds: float = 60.0


DEFAULT_DURATION_LIMITS = DurationLimits()


def cut_points_for_word_range(words: Sequence[TranscribedWord], word_range: WordRange) -> tuple[float, float]:
    """Pads around the spoken words, but never into the neighbouring words."""
    first_word = words[word_range.first_word_index]
    last_word = words[word_range.last_word_index]
    has_previous_word = word_range.first_word_index > 0
    has_next_word = word_range.last_word_index + 1 < len(words)
    previous_word_end = words[word_range.first_word_index - 1].end_seconds if has_previous_word else 0.0
    next_word_start = words[word_range.last_word_index + 1].start_seconds if has_next_word else float("inf")
    start_seconds = max(previous_word_end, first_word.start_seconds - LEAD_PADDING_SECONDS, 0.0)
    end_seconds = min(next_word_start, last_word.end_seconds + TAIL_PADDING_SECONDS)
    return start_seconds, end_seconds


def span_seconds(words: Sequence[TranscribedWord], word_range: WordRange) -> float:
    start_seconds, end_seconds = cut_points_for_word_range(words, word_range)
    return end_seconds - start_seconds


def extend_until_long_enough(
    words: Sequence[TranscribedWord], word_range: WordRange, limits: DurationLimits
) -> WordRange | None:
    """Grows forward first (the story usually continues), then backward. None if the video is too short."""
    first_index, last_index = word_range.first_word_index, word_range.last_word_index
    while span_seconds(words, WordRange(first_index, last_index)) < limits.minimum_seconds:
        if last_index + 1 < len(words):
            last_index += 1
        elif first_index > 0:
            first_index -= 1
        else:
            return None
    return WordRange(first_index, last_index)


def shrink_until_short_enough(
    words: Sequence[TranscribedWord], word_range: WordRange, limits: DurationLimits
) -> WordRange:
    last_index = word_range.last_word_index
    while (
        last_index > word_range.first_word_index
        and span_seconds(words, WordRange(word_range.first_word_index, last_index)) > limits.maximum_seconds
    ):
        last_index -= 1
    return WordRange(word_range.first_word_index, last_index)


def snap_end_to_sentence_boundary(
    words: Sequence[TranscribedWord], word_range: WordRange, limits: DurationLimits
) -> WordRange:
    """Prefers the latest sentence end that keeps the clip in range, so clips finish a thought."""
    for candidate_last_index in range(word_range.last_word_index, word_range.first_word_index - 1, -1):
        candidate_range = WordRange(word_range.first_word_index, candidate_last_index)
        if span_seconds(words, candidate_range) < limits.minimum_seconds:
            break
        if words[candidate_last_index].ends_sentence:
            return candidate_range
    return extend_to_next_sentence_end(words, word_range, limits)


def extend_to_next_sentence_end(
    words: Sequence[TranscribedWord], word_range: WordRange, limits: DurationLimits
) -> WordRange:
    for candidate_last_index in range(word_range.last_word_index, len(words)):
        candidate_range = WordRange(word_range.first_word_index, candidate_last_index)
        if span_seconds(words, candidate_range) > limits.maximum_seconds:
            break
        if words[candidate_last_index].ends_sentence:
            return candidate_range
    return word_range


def fit_word_range_to_duration(
    words: Sequence[TranscribedWord], word_range: WordRange, limits: DurationLimits = DEFAULT_DURATION_LIMITS
) -> WordRange | None:
    long_enough_range = extend_until_long_enough(words, word_range, limits)
    if long_enough_range is None:
        return None
    short_enough_range = shrink_until_short_enough(words, long_enough_range, limits)
    return snap_end_to_sentence_boundary(words, short_enough_range, limits)


def word_range_covering(words: Sequence[TranscribedWord], start_seconds: float, end_seconds: float) -> WordRange | None:
    """The words spoken between two timestamps, e.g. from a hand-picked cut."""
    inside_indices = [
        index
        for index, word in enumerate(words)
        if word.end_seconds > start_seconds and word.start_seconds < end_seconds
    ]
    return WordRange(inside_indices[0], inside_indices[-1]) if inside_indices else None
