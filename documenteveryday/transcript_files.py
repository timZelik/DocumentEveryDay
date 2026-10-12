"""Saves and loads transcripts as JSON, so a re-run never pays for transcription twice."""

import json
from dataclasses import asdict
from pathlib import Path

from documenteveryday.domain import TranscribedWord, Transcript


def save_transcript(transcript: Transcript, transcript_path: Path) -> None:
    """Written to a temporary name and renamed, so a crash mid-write never leaves a half transcript."""
    transcript_path.parent.mkdir(parents=True, exist_ok=True)
    partial_path = transcript_path.with_name(transcript_path.name + ".partial")
    partial_path.write_text(
        json.dumps(
            {
                "source_video_id": transcript.source_video_id,
                "words": [asdict(word) for word in transcript.words],
            },
            ensure_ascii=False,
        )
    )
    partial_path.replace(transcript_path)


def load_transcript(transcript_path: Path) -> Transcript:
    stored = json.loads(transcript_path.read_text())
    return Transcript(
        source_video_id=stored["source_video_id"],
        words=tuple(TranscribedWord(**word) for word in stored["words"]),
    )
