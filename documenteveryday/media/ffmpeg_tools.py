"""Thin, testable wrappers around the ffmpeg and ffprobe binaries."""

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


class FfmpegFailed(RuntimeError):
    pass


@dataclass(frozen=True)
class VideoDimensions:
    width: int
    height: int


def run_ffmpeg(arguments: list[str], working_directory: Path | None = None) -> str:
    """Runs ffmpeg quietly and returns its stderr, where ffmpeg writes filter reports."""
    completed_process = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostdin", *arguments],
        cwd=working_directory,
        capture_output=True,
        text=True,
    )
    if completed_process.returncode != 0:
        raise FfmpegFailed(completed_process.stderr[-2000:])
    return completed_process.stderr


def probe_stream_metadata(media_path: Path) -> dict:
    completed_process = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(media_path)],
        capture_output=True,
        text=True,
    )
    if completed_process.returncode != 0:
        raise FfmpegFailed(completed_process.stderr[-2000:])
    return json.loads(completed_process.stdout)


def probe_duration_seconds(media_path: Path) -> float:
    return float(probe_stream_metadata(media_path)["format"]["duration"])


def probe_video_dimensions(media_path: Path) -> VideoDimensions:
    video_stream = next(
        stream for stream in probe_stream_metadata(media_path)["streams"] if stream["codec_type"] == "video"
    )
    return VideoDimensions(width=int(video_stream["width"]), height=int(video_stream["height"]))
