"""Turns scored moments into concrete, non-overlapping clip plans that obey the 15-60s word-boundary rules."""

from collections import Counter
from collections.abc import Sequence

from documenteveryday.domain import ClipPlan, ScoredMoment, Segment, SegmentClassification, SegmentTag, Transcript
from documenteveryday.selection.word_boundary_window import (
    DEFAULT_DURATION_LIMITS,
    DurationLimits,
    WordRange,
    cut_points_for_word_range,
    fit_word_range_to_duration,
)


def segments_in_moment(moment: ScoredMoment, segments_by_index: dict[int, Segment]) -> list[Segment] | None:
    """None when the model pointed at missing segments, a backwards range, or across two videos."""
    indices = range(moment.first_segment_index, moment.last_segment_index + 1)
    moment_segments = [segments_by_index.get(index) for index in indices]
    if not moment_segments or None in moment_segments:
        return None
    if len({segment.source_video_id for segment in moment_segments}) != 1:
        return None
    return moment_segments


def dominant_classification(
    moment_segments: list[Segment], classifications: dict[int, SegmentClassification]
) -> SegmentClassification:
    segment_classifications = [
        classifications[segment.index] for segment in moment_segments if segment.index in classifications
    ]
    if not segment_classifications:
        return SegmentClassification(SegmentTag.OTHER, "")
    most_common_tag, _ = Counter(item.tag for item in segment_classifications).most_common(1)[0]
    return next(item for item in segment_classifications if item.tag == most_common_tag)


def plan_for_moment(
    moment: ScoredMoment,
    segments_by_index: dict[int, Segment],
    transcripts_by_video: dict[int, Transcript],
    classifications: dict[int, SegmentClassification],
    limits: DurationLimits,
) -> ClipPlan | None:
    moment_segments = segments_in_moment(moment, segments_by_index)
    if moment_segments is None:
        return None
    words = transcripts_by_video[moment_segments[0].source_video_id].words
    spoken_range = WordRange(moment_segments[0].first_word_index, moment_segments[-1].last_word_index)
    fitted_range = fit_word_range_to_duration(words, spoken_range, limits)
    if fitted_range is None:
        return None
    start_seconds, end_seconds = cut_points_for_word_range(words, fitted_range)
    classification = dominant_classification(moment_segments, classifications)
    return ClipPlan(
        source_video_id=moment_segments[0].source_video_id,
        first_word_index=fitted_range.first_word_index,
        last_word_index=fitted_range.last_word_index,
        start_seconds=start_seconds,
        end_seconds=end_seconds,
        tag=classification.tag,
        tag_reason=classification.reason,
        score=moment.score,
        criteria=moment.criteria,
        pick_reason=moment.reason,
        privacy_concern=moment.privacy_concern,
    )


def plans_overlap(first_plan: ClipPlan, second_plan: ClipPlan) -> bool:
    return (
        first_plan.source_video_id == second_plan.source_video_id
        and first_plan.start_seconds < second_plan.end_seconds
        and second_plan.start_seconds < first_plan.end_seconds
    )


def select_clip_plans(
    moments: Sequence[ScoredMoment],
    segments: Sequence[Segment],
    transcripts: Sequence[Transcript],
    classifications: dict[int, SegmentClassification],
    maximum_clips: int,
    minimum_score: int,
    limits: DurationLimits = DEFAULT_DURATION_LIMITS,
) -> list[ClipPlan]:
    segments_by_index = {segment.index: segment for segment in segments}
    transcripts_by_video = {transcript.source_video_id: transcript for transcript in transcripts}
    chosen_plans: list[ClipPlan] = []
    for moment in sorted(moments, key=lambda candidate: candidate.score, reverse=True):
        if len(chosen_plans) >= maximum_clips or moment.score < minimum_score:
            break
        plan = plan_for_moment(moment, segments_by_index, transcripts_by_video, classifications, limits)
        if plan and not any(plans_overlap(plan, chosen) for chosen in chosen_plans):
            chosen_plans.append(plan)
    return chosen_plans
