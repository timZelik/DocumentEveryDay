"""Splits a transcript into segments at natural pauses and sentence ends, so each can be tagged alone."""

from documenteveryday.domain import Segment, TranscribedWord, Transcript

PAUSE_THAT_ENDS_SEGMENT_SECONDS = 1.2
TARGET_SEGMENT_SECONDS = 20.0
MAXIMUM_SEGMENT_SECONDS = 40.0


def should_close_segment(
    segment_first_word: TranscribedWord, previous_word: TranscribedWord, next_word: TranscribedWord
) -> bool:
    segment_duration = previous_word.end_seconds - segment_first_word.start_seconds
    return (
        next_word.start_seconds - previous_word.end_seconds > PAUSE_THAT_ENDS_SEGMENT_SECONDS
        or (segment_duration >= TARGET_SEGMENT_SECONDS and previous_word.ends_sentence)
        or next_word.end_seconds - segment_first_word.start_seconds > MAXIMUM_SEGMENT_SECONDS
    )


def group_word_indices(words: tuple[TranscribedWord, ...]) -> list[list[int]]:
    groups: list[list[int]] = []
    for index, word in enumerate(words):
        if not groups or should_close_segment(words[groups[-1][0]], words[groups[-1][-1]], word):
            groups.append([])
        groups[-1].append(index)
    return groups


def split_into_segments(transcript: Transcript, first_segment_index: int) -> list[Segment]:
    return [
        Segment(
            index=first_segment_index + position,
            source_video_id=transcript.source_video_id,
            first_word_index=indices[0],
            last_word_index=indices[-1],
            words=tuple(transcript.words[index] for index in indices),
        )
        for position, indices in enumerate(group_word_indices(transcript.words))
    ]


def split_transcripts_into_segments(transcripts: list[Transcript]) -> list[Segment]:
    """Segment indices run across every video in the batch, so the AI can refer to them unambiguously."""
    segments: list[Segment] = []
    for transcript in transcripts:
        segments.extend(split_into_segments(transcript, first_segment_index=len(segments)))
    return segments
