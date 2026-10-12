"""Finds stretches of black frames, a cheap stand-in for 'the camera was covered or pointed at nothing'."""

import re
from pathlib import Path

from documenteveryday.media.ffmpeg_tools import run_ffmpeg

BLACK_INTERVAL_PATTERN = re.compile(r"black_start:(?P<start>[\d.]+) black_end:(?P<end>[\d.]+)")


def find_black_intervals(video_path: Path, minimum_seconds: float = 1.0) -> list[tuple[float, float]]:
    filter_report = run_ffmpeg(
        [
            "-i",
            str(video_path),
            "-vf",
            f"blackdetect=d={minimum_seconds}:pix_th=0.10",
            "-an",
            "-f",
            "null",
            "-",
        ]
    )
    return [
        (float(match["start"]), float(match["end"]))
        for match in BLACK_INTERVAL_PATTERN.finditer(filter_report)
    ]
