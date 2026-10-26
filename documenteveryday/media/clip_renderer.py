"""Cuts one 9:16 clip out of a source video, burning in an ASS subtitle file if given.

Only the chosen window is ever decoded and encoded, never the whole evening of footage.
"""

from dataclasses import dataclass
from pathlib import Path

from documenteveryday.media.ffmpeg_tools import run_ffmpeg

VERTICAL_WIDTH = 1080
VERTICAL_HEIGHT = 1920

VIDEO_ENCODER_ARGUMENTS = {
    "libx264": ["-c:v", "libx264", "-preset", "veryfast", "-crf", "21"],
    "h264_videotoolbox": ["-c:v", "h264_videotoolbox", "-b:v", "10M"],
}


@dataclass(frozen=True)
class ClipRenderRequest:
    source_path: Path
    start_seconds: float
    end_seconds: float
    output_path: Path
    subtitles_path: Path | None = None
    replacement_audio_path: Path | None = None
    video_encoder: str = "libx264"


def build_video_filter(subtitles_filename: str | None) -> str:
    fill_vertical_frame = (
        f"scale={VERTICAL_WIDTH}:{VERTICAL_HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={VERTICAL_WIDTH}:{VERTICAL_HEIGHT},setsar=1"
    )
    return f"{fill_vertical_frame},subtitles={subtitles_filename}" if subtitles_filename else fill_vertical_frame


def build_audio_arguments(replacement_audio_path: Path | None) -> list[str]:
    """Mode A keeps my own narration. The voiceover seam (modes B and C) swaps in another track."""
    if replacement_audio_path is None:
        return ["-map", "0:v:0", "-map", "0:a:0?"]
    return ["-i", str(replacement_audio_path.resolve()), "-map", "0:v:0", "-map", "1:a:0", "-shortest"]


def build_ffmpeg_arguments(request: ClipRenderRequest) -> list[str]:
    subtitles_filename = request.subtitles_path.name if request.subtitles_path else None
    return [
        "-y",
        "-ss", f"{request.start_seconds:.3f}",
        "-i", str(request.source_path.resolve()),
        *build_audio_arguments(request.replacement_audio_path),
        "-t", f"{request.end_seconds - request.start_seconds:.3f}",
        "-vf", build_video_filter(subtitles_filename),
        *VIDEO_ENCODER_ARGUMENTS[request.video_encoder],
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k",
        "-movflags", "+faststart",
        str(request.output_path.resolve()),
    ]  # fmt: skip


def render_vertical_clip(request: ClipRenderRequest) -> Path:
    """ffmpeg runs inside the subtitle folder so the subtitles filter never needs path escaping."""
    request.output_path.parent.mkdir(parents=True, exist_ok=True)
    working_directory = request.subtitles_path.parent if request.subtitles_path else None
    run_ffmpeg(build_ffmpeg_arguments(request), working_directory=working_directory)
    return request.output_path
