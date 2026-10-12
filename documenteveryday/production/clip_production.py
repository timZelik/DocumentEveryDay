"""Writes a clip's subtitle file and renders the clip: the one place the pipeline and QA tools both use."""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from documenteveryday.captions.ass_subtitles import render_ass_document
from documenteveryday.domain import CaptionCue
from documenteveryday.media.clip_renderer import ClipRenderRequest, render_vertical_clip


@dataclass(frozen=True)
class ClipProductionRequest:
    source_path: Path
    start_seconds: float
    end_seconds: float
    cues: Sequence[CaptionCue]
    hook_line: str
    output_directory: Path
    clip_name: str
    video_encoder: str = "libx264"
    replacement_audio_path: Path | None = None


def write_subtitles_file(request: ClipProductionRequest) -> Path:
    subtitles_path = request.output_directory / f"{request.clip_name}.ass"
    subtitles_path.parent.mkdir(parents=True, exist_ok=True)
    clip_duration = request.end_seconds - request.start_seconds
    subtitles_path.write_text(render_ass_document(request.cues, request.hook_line, clip_duration))
    return subtitles_path


def produce_clip(request: ClipProductionRequest) -> Path:
    return render_vertical_clip(
        ClipRenderRequest(
            source_path=request.source_path,
            start_seconds=request.start_seconds,
            end_seconds=request.end_seconds,
            output_path=request.output_directory / f"{request.clip_name}.mp4",
            subtitles_path=write_subtitles_file(request),
            replacement_audio_path=request.replacement_audio_path,
            video_encoder=request.video_encoder,
        )
    )
