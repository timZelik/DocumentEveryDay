"""Speech to timed words. The Protocol lets tests (or a faster Mac-native model later) stand in."""

from pathlib import Path
from typing import Protocol

from documenteveryday.domain import TranscribedWord, Transcript


class Transcriber(Protocol):
    def transcribe(self, media_path: Path, source_video_id: int) -> Transcript: ...


class FasterWhisperTranscriber:
    """Free, local, CPU transcription. Multilingual mode re-detects language per segment, so the few
    seconds of Egyptian Arabic come out in Arabic script instead of being forced into English."""

    def __init__(self, model_size: str = "small", compute_type: str = "int8"):
        self.model_size = model_size
        self.compute_type = compute_type
        self.loaded_model = None

    def model(self):
        if self.loaded_model is None:
            from faster_whisper import WhisperModel  # heavy import, only when transcription actually runs

            self.loaded_model = WhisperModel(self.model_size, device="cpu", compute_type=self.compute_type)
        return self.loaded_model

    def transcribe(self, media_path: Path, source_video_id: int) -> Transcript:
        whisper_segments, _ = self.model().transcribe(
            str(media_path), word_timestamps=True, vad_filter=True, multilingual=True, beam_size=5
        )
        words = tuple(
            TranscribedWord(word.word.strip(), word.start, word.end, word.probability)
            for segment in whisper_segments
            for word in (segment.words or [])
            if word.word.strip()
        )
        return Transcript(source_video_id=source_video_id, words=words)
