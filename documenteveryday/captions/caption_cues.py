"""Groups a clip's words into short, readable caption cues, timed relative to the clip start."""

from collections.abc import Sequence

from documenteveryday.domain import CaptionCue, TranscribedWord

MAXIMUM_WORDS_PER_CUE = 4
MAXIMUM_CHARACTERS_PER_LINE = 24
MAXIMUM_LINES_PER_CUE = 2
PAUSE_THAT_BREAKS_CUE_SECONDS = 0.6


def should_start_new_cue(current_cue_words: list[TranscribedWord], next_word: TranscribedWord) -> bool:
    if not current_cue_words:
        return False
    previous_word = current_cue_words[-1]
    joined_length = len(" ".join(word.text.strip() for word in [*current_cue_words, next_word]))
    return (
        len(current_cue_words) >= MAXIMUM_WORDS_PER_CUE
        or joined_length > MAXIMUM_CHARACTERS_PER_LINE
        or next_word.start_seconds - previous_word.end_seconds > PAUSE_THAT_BREAKS_CUE_SECONDS
        or next_word.is_arabic != previous_word.is_arabic
        or previous_word.ends_sentence
    )


def group_words_into_cue_runs(words: Sequence[TranscribedWord]) -> list[list[TranscribedWord]]:
    word_runs: list[list[TranscribedWord]] = []
    for word in words:
        if not word_runs or should_start_new_cue(word_runs[-1], word):
            word_runs.append([])
        word_runs[-1].append(word)
    return word_runs


def cue_from_word_run(word_run: list[TranscribedWord], clip_start: float, clip_duration: float) -> CaptionCue:
    return CaptionCue(
        start_seconds=min(max(word_run[0].start_seconds - clip_start, 0.0), clip_duration),
        end_seconds=min(max(word_run[-1].end_seconds - clip_start, 0.0), clip_duration),
        text=" ".join(word.text.strip() for word in word_run),
        is_arabic=word_run[0].is_arabic,
    )


def close_gaps_between_cues(cues: list[CaptionCue]) -> list[CaptionCue]:
    """Holds each caption on screen until the next one starts, so captions don't flicker between words."""
    held_cues = []
    for cue, next_cue in zip(cues, [*cues[1:], None], strict=True):
        hold_until = next_cue.start_seconds if next_cue else cue.end_seconds
        if hold_until - cue.end_seconds <= PAUSE_THAT_BREAKS_CUE_SECONDS:
            cue = CaptionCue(cue.start_seconds, hold_until, cue.text, cue.is_arabic, cue.english_translation)
        held_cues.append(cue)
    return held_cues


def build_caption_cues(words: Sequence[TranscribedWord], clip_start: float, clip_end: float) -> list[CaptionCue]:
    words_inside_clip = [word for word in words if word.end_seconds > clip_start and word.start_seconds < clip_end]
    clip_duration = clip_end - clip_start
    cues = [
        cue_from_word_run(word_run, clip_start, clip_duration)
        for word_run in group_words_into_cue_runs(words_inside_clip)
    ]
    return close_gaps_between_cues(cues)


def wrap_caption_text(text: str, maximum_line_characters: int = MAXIMUM_CHARACTERS_PER_LINE) -> list[str]:
    lines: list[str] = []
    for word in text.split():
        if lines and len(lines[-1]) + 1 + len(word) <= maximum_line_characters:
            lines[-1] = f"{lines[-1]} {word}"
        else:
            lines.append(word)
    return lines


def displayed_lines(cue: CaptionCue) -> list[str]:
    """Arabic cues show the original script above its English translation."""
    if cue.is_arabic and cue.english_translation:
        return [cue.text, *wrap_caption_text(cue.english_translation)]
    return wrap_caption_text(cue.text)
