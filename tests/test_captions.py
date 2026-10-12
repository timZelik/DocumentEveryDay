from documenteveryday.captions.ass_subtitles import format_ass_timestamp, render_ass_document
from documenteveryday.captions.caption_cues import build_caption_cues, displayed_lines, wrap_caption_text
from documenteveryday.domain import CaptionCue, TranscribedWord
from tests.conftest import evenly_spoken_words


def test_cues_are_short_relative_to_clip_and_split_at_sentence_ends():
    words = evenly_spoken_words(["one two three four five six", "seven eight"], start=10.0)
    cues = build_caption_cues(words, clip_start=10.0, clip_end=14.0)
    assert [cue.text for cue in cues] == ["one two three four", "five six.", "seven eight."]
    assert cues[0].start_seconds == 0.0
    assert all(cue.end_seconds <= 4.0 for cue in cues)


def test_cues_hold_until_the_next_cue_to_avoid_flicker():
    words = evenly_spoken_words(["one two three four five six"])
    cues = build_caption_cues(words, 0.0, 3.0)
    assert cues[0].end_seconds == cues[1].start_seconds


def test_arabic_words_get_their_own_cue():
    words = (
        TranscribedWord("I", 0.0, 0.2),
        TranscribedWord("said", 0.3, 0.5),
        TranscribedWord("ازيك", 0.6, 1.0),
        TranscribedWord("today.", 1.1, 1.4),
    )
    cues = build_caption_cues(words, 0.0, 2.0)
    assert [(cue.text, cue.is_arabic) for cue in cues] == [
        ("I said", False),
        ("ازيك", True),
        ("today.", False),
    ]


def test_arabic_cue_displays_original_above_translation():
    cue = CaptionCue(0, 1, "ازيك", is_arabic=True, english_translation="How are you")
    assert displayed_lines(cue) == ["ازيك", "How are you"]


def test_wrap_caption_text_respects_line_length():
    assert wrap_caption_text("the quick brown fox jumps over", 12) == ["the quick", "brown fox", "jumps over"]


def test_ass_document_contains_hook_and_escaped_cues():
    document = render_ass_document([CaptionCue(0.5, 1.5, "use {braces}")], "Day 12 of lifting", 20.0)
    assert "Dialogue: 0,0:00:00.00,0:00:03.50,Hook,,0,0,0,,Day 12 of lifting" in document
    assert "use (braces)" in document


def test_ass_timestamp_format():
    assert format_ass_timestamp(3725.456) == "1:02:05.46"
