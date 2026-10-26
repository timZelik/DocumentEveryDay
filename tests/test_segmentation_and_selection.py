from documenteveryday.classification.segment_classifier import parse_classifications
from documenteveryday.domain import (
    GoodClipCriterion,
    ScoredMoment,
    SegmentClassification,
    SegmentTag,
    TranscribedWord,
    Transcript,
)
from documenteveryday.segmentation.segmenter import split_transcripts_into_segments
from documenteveryday.selection.clip_selector import select_clip_plans
from documenteveryday.selection.moment_scorer import parse_moments
from tests.conftest import evenly_spoken_words


def transcript_with_pause(source_video_id: int) -> Transcript:
    first_part = evenly_spoken_words(["warm up set done"] * 10)
    second_part = evenly_spoken_words(["now the heavy set"] * 10, start=first_part[-1].end_seconds + 3.0)
    return Transcript(source_video_id, first_part + second_part)


def test_segments_split_at_long_pauses_and_number_across_videos():
    segments = split_transcripts_into_segments([transcript_with_pause(1), transcript_with_pause(2)])
    assert [segment.index for segment in segments] == list(range(len(segments)))
    assert {segment.source_video_id for segment in segments} == {1, 2}
    first_video_segments = [segment for segment in segments if segment.source_video_id == 1]
    assert first_video_segments[0].text.startswith("warm up")
    assert any(segment.text.startswith("now the heavy") for segment in first_video_segments)
    assert all(segment.end_seconds - segment.start_seconds <= 40 for segment in segments)


def test_segments_never_exceed_maximum_length_without_pauses():
    words = tuple(TranscribedWord("go", index * 0.5, index * 0.5 + 0.4) for index in range(400))
    segments = split_transcripts_into_segments([Transcript(1, words)])
    assert all(segment.end_seconds - segment.start_seconds <= 40 for segment in segments)


def test_classifier_parse_drops_unknown_indices_and_fills_missing_ones():
    segments = split_transcripts_into_segments([transcript_with_pause(1)])
    response = {"classifications": [{"segment_index": 0, "tag": "training", "reason": "lifting"},
                                    {"segment_index": 999, "tag": "arabic", "reason": "made up"}]}  # fmt: skip
    classifications = parse_classifications(response, segments)
    assert classifications[0].tag == SegmentTag.TRAINING
    assert 999 not in classifications
    assert classifications[1] == SegmentClassification(SegmentTag.OTHER, "Not tagged by the classifier.")


def test_scorer_parse_clamps_scores_and_dedupes_criteria():
    [moment] = parse_moments(
        {"moments": [{"first_segment_index": 0, "last_segment_index": 1, "score": 42,
                      "criteria": ["EFFORT", "EFFORT"], "reason": "r", "privacy_concern": " "}]}
    )  # fmt: skip
    assert moment.score == 10 and moment.criteria == (GoodClipCriterion.EFFORT,) and moment.privacy_concern == ""


def test_selector_picks_best_non_overlapping_valid_moments():
    transcripts = [transcript_with_pause(1), transcript_with_pause(2)]
    segments = split_transcripts_into_segments(transcripts)
    last_index_video_1 = max(segment.index for segment in segments if segment.source_video_id == 1)
    classifications = {segment.index: SegmentClassification(SegmentTag.TRAINING, "gym") for segment in segments}
    moments = [
        ScoredMoment(0, 0, 9, (GoodClipCriterion.EFFORT,), "best"),
        ScoredMoment(0, 0, 8, (), "overlaps the best"),
        ScoredMoment(last_index_video_1, last_index_video_1 + 1, 8, (), "crosses two videos"),
        ScoredMoment(last_index_video_1 + 1, last_index_video_1 + 1, 7, (), "second video"),
        ScoredMoment(0, 0, 2, (), "below minimum score"),
    ]
    plans = select_clip_plans(moments, segments, transcripts, classifications, maximum_clips=10, minimum_score=5)
    assert [plan.pick_reason for plan in plans] == ["best", "second video"]
    assert all(15 <= plan.duration_seconds <= 60 for plan in plans)
    assert plans[0].tag == SegmentTag.TRAINING
