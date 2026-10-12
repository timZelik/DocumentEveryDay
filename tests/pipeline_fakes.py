"""Fakes for running the whole pipeline in tests: scripted words and scripted Claude answers."""

import re

from documenteveryday.classification.segment_classifier import CLASSIFIER_SYSTEM_PROMPT
from documenteveryday.domain import TranscribedWord, Transcript
from tests.conftest import evenly_spoken_words
from tests.fake_claude import json_response

SEGMENT_INDEX_PATTERN = re.compile(r"^\[(\d+)\]", re.MULTILINE)


class FakeTranscriber:
    """Thirty-odd seconds of talk with a pause in the middle, plus a few Arabic words."""

    def __init__(self):
        self.transcribed_paths = []

    def transcribe(self, media_path, source_video_id) -> Transcript:
        self.transcribed_paths.append(media_path)
        opening = evenly_spoken_words(["okay this is my last heavy set of the night"] * 3, start=1.0)
        arabic = (TranscribedWord("ازيك", 17.0, 17.6), TranscribedWord("يا", 17.7, 17.9))
        lesson = evenly_spoken_words(["what I learned is to brace before every rep"] * 4, start=18.5)
        return Transcript(source_video_id, opening + arabic + lesson)


def classify_every_segment(request: dict):
    indices = [int(index) for index in SEGMENT_INDEX_PATTERN.findall(request["messages"][0]["content"])]
    return json_response(
        {"classifications": [{"segment_index": index, "tag": "training", "reason": "lifting"} for index in indices]}
    )


def score_first_segment(request: dict):
    return json_response(
        {
            "moments": [
                {"first_segment_index": 0, "last_segment_index": 0, "score": 9, "criteria": ["EFFORT", "LESSON"],
                 "reason": "Last heavy set plus the bracing lesson.", "privacy_concern": ""}
            ]
        }
    )  # fmt: skip


def analysis_routes() -> dict:
    return {CLASSIFIER_SYSTEM_PROMPT[:60]: classify_every_segment, "You pick the best moments": score_first_segment}
