import shutil
import subprocess
from pathlib import Path

import pytest

from documenteveryday.domain import TranscribedWord


def evenly_spoken_words(sentence_texts: list[str], seconds_per_word: float = 0.5, start: float = 0.0):
    """Builds back-to-back words; each sentence's last word ends with a period."""
    words, clock = [], start
    for sentence in sentence_texts:
        sentence_words = sentence.split()
        for position, text in enumerate(sentence_words):
            is_last = position == len(sentence_words) - 1
            words.append(
                TranscribedWord(text + ("." if is_last else ""), clock, clock + seconds_per_word * 0.9)
            )
            clock += seconds_per_word
    return tuple(words)


@pytest.fixture(scope="session")
def synthetic_landscape_video(tmp_path_factory) -> Path:
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg is not installed")
    video_path = tmp_path_factory.mktemp("media") / "landscape.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=30:duration=40",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=40",
         "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", str(video_path)],
        check=True,
    )  # fmt: skip
    return video_path
