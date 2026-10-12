"""How transcript pieces are shown to Claude: compact, indexed lines it can refer back to."""

from collections.abc import Sequence

from documenteveryday.domain import Segment, SegmentClassification


def format_timestamp(seconds: float) -> str:
    minutes, whole_seconds = divmod(int(seconds), 60)
    return f"{minutes}:{whole_seconds:02d}"


def describe_segment(segment: Segment, classification: SegmentClassification | None = None) -> str:
    duration = segment.end_seconds - segment.start_seconds
    tag_note = f" [{classification.tag.value}]" if classification else ""
    return (
        f"[{segment.index}] video {segment.source_video_id} {format_timestamp(segment.start_seconds)}-"
        f"{format_timestamp(segment.end_seconds)} ({duration:.0f}s){tag_note}: {segment.text}"
    )


def describe_segments(
    segments: Sequence[Segment], classifications: dict[int, SegmentClassification] | None = None
) -> str:
    classifications = classifications or {}
    return "\n".join(describe_segment(segment, classifications.get(segment.index)) for segment in segments)
