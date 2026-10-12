from pathlib import Path

from documenteveryday.domain import CaptionCue, ClipPlan, TranscribedWord
from documenteveryday.qa.clip_checks import (
    ClipUnderReview,
    find_caption_problems,
    find_cuts_mid_word,
    find_dead_air,
    find_duration_out_of_range,
    find_unfinished_sentence,
)
from tests.conftest import evenly_spoken_words

WORDS = evenly_spoken_words(["one two three four five six seven eight nine ten"] * 6)


def clip_for(first_index, last_index, start=None, end=None, cues=(), words=WORDS) -> ClipUnderReview:
    start = words[first_index].start_seconds if start is None else start
    end = words[last_index].end_seconds if end is None else end
    return ClipUnderReview(ClipPlan(1, first_index, last_index, start, end), words, tuple(cues), Path("unused.mp4"))


def codes(problems) -> list[str]:
    return [problem.code for problem in problems]


def test_cut_inside_a_word_is_caught():
    assert codes(find_cuts_mid_word(clip_for(0, 39, start=WORDS[0].start_seconds + 0.2))) == ["CUT_MID_WORD"]
    assert find_cuts_mid_word(clip_for(0, 39)) == []


def test_ending_before_the_sentence_finishes_is_caught():
    assert codes(find_unfinished_sentence(clip_for(0, 38))) == ["ENDS_MID_SENTENCE"]
    assert find_unfinished_sentence(clip_for(0, 39)) == []


def test_dead_air_inside_and_at_edges_is_caught():
    gappy_words = (TranscribedWord("hi", 0.0, 0.5), TranscribedWord("there.", 4.0, 4.5))
    clip = clip_for(0, 1, start=0.0, end=6.0, words=gappy_words)
    assert codes(find_dead_air(clip)) == ["DEAD_AIR", "DEAD_AIR"]


def test_duration_outside_fifteen_to_sixty_seconds_is_caught():
    assert codes(find_duration_out_of_range(clip_for(0, 9))) == ["DURATION_OUT_OF_RANGE"]
    assert find_duration_out_of_range(clip_for(0, 39)) == []


def test_long_and_untranslated_captions_are_caught():
    cues = [
        CaptionCue(0, 1, "this caption is far far far too long to fit on two lines of the screen at all"),
        CaptionCue(1, 2, "ازيك", is_arabic=True),
        CaptionCue(2, 3, "fine"),
    ]
    assert codes(find_caption_problems(clip_for(0, 39, cues=cues))) == ["CAPTION_OVERFLOW", "UNTRANSLATED_ARABIC"]
