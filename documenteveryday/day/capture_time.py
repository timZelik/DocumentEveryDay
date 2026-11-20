"""When a clip was recorded, so the mosaic fills in the order the day happened."""

from datetime import datetime
from pathlib import Path

from documenteveryday.media.ffmpeg_tools import FfmpegFailed, probe_stream_metadata

CREATION_TAGS = ("com.apple.quicktime.creationdate", "creation_time")


def parse_timestamp(text: str) -> datetime | None:
    try:
        return datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except ValueError:
        return None


def capture_timestamp(video_path: Path) -> float:
    try:
        tags = probe_stream_metadata(video_path).get("format", {}).get("tags", {})
    except FfmpegFailed:
        tags = {}
    lowered = {key.lower(): value for key, value in tags.items()}
    for tag in CREATION_TAGS:
        parsed = parse_timestamp(lowered.get(tag, ""))
        if parsed is not None:
            return parsed.timestamp()
    return video_path.stat().st_mtime
