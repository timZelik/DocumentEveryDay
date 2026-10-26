from documenteveryday.domain import TranscribedWord
from documenteveryday.selection.word_boundary_window import (
    DurationLimits,
    WordRange,
    cut_points_for_word_range,
    fit_word_range_to_duration,
    word_range_covering,
)
from tests.conftest import evenly_spoken_words


def test_cut_points_pad_into_silence_but_never_into_neighbouring_words():
    words = (
        TranscribedWord("one", 0.0, 1.0),
        TranscribedWord("two", 1.05, 2.0),
        TranscribedWord("three.", 5.0, 6.0),
    )
    start_seconds, end_seconds = cut_points_for_word_range(words, WordRange(1, 1))
    assert start_seconds == 1.0  # previous word ends at 1.0, padding would have cut into it
    assert end_seconds == 2.3  # a full tail pad fits before "three"


def test_short_range_grows_to_minimum_and_ends_on_a_sentence():
    words = evenly_spoken_words(["this is the first sentence here"] * 20)
    fitted = fit_word_range_to_duration(words, WordRange(0, 3), DurationLimits(15, 60))
    start_seconds, end_seconds = cut_points_for_word_range(words, fitted)
    assert 15 <= end_seconds - start_seconds <= 60
    assert words[fitted.last_word_index].ends_sentence


def test_long_range_shrinks_below_maximum():
    words = evenly_spoken_words(["a b c d e f g h i j"] * 30)
    fitted = fit_word_range_to_duration(words, WordRange(0, len(words) - 1), DurationLimits(15, 60))
    start_seconds, end_seconds = cut_points_for_word_range(words, fitted)
    assert end_seconds - start_seconds <= 60
    assert words[fitted.last_word_index].ends_sentence


def test_video_too_short_for_minimum_returns_none():
    words = evenly_spoken_words(["too short."])
    assert fit_word_range_to_duration(words, WordRange(0, 1), DurationLimits(15, 60)) is None


def test_word_range_covering_finds_words_inside_timestamps():
    words = evenly_spoken_words(["zero one two three four"])
    assert word_range_covering(words, 0.6, 1.6) == WordRange(1, 3)
    assert word_range_covering(words, 100, 200) is None


def test_short_moment_never_grows_across_a_long_silence_into_another_moment():
    meal_prep = evenly_spoken_words(["chicken rice and broccoli done"] * 5)  # about 12.5 seconds
    arabic_after_silence = evenly_spoken_words(["now arabic study"] * 10, start=meal_prep[-1].end_seconds + 27)
    words = meal_prep + arabic_after_silence
    assert fit_word_range_to_duration(words, WordRange(0, len(meal_prep) - 1), DurationLimits(15, 60)) is None


def test_short_moment_still_grows_across_normal_pauses():
    first = evenly_spoken_words(["chicken rice and broccoli done"] * 5)
    more = evenly_spoken_words(["seasoned the rice while it cooked"] * 5, start=first[-1].end_seconds + 1.5)
    fitted = fit_word_range_to_duration(first + more, WordRange(0, len(first) - 1), DurationLimits(15, 60))
    assert fitted is not None and fitted.last_word_index >= len(first)
