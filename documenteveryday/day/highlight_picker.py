"""Picks the best few seconds of a clip with no AI at all: local motion analysis on tiny grey frames.

The busiest window usually shows the action (folding, vacuuming, running). Two guards keep it honest: the
first and last half second are skipped (fumbling with the record button), and dark windows (camera in a
pocket) are penalised. Motion spikes are capped so a whip pan does not beat steady action.
"""

import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy

from documenteveryday.media.ffmpeg_tools import FfmpegFailed, probe_duration_seconds

ANALYSIS_FRAMES_PER_SECOND = 5
ANALYSIS_WIDTH = 48
ANALYSIS_HEIGHT = 64
EDGE_SKIP_SECONDS = 0.5
DARK_LUMA = 35.0


@dataclass(frozen=True)
class Highlight:
    start_seconds: float
    duration_seconds: float
    motion_score: float


def grey_frames(video_path: Path) -> numpy.ndarray:
    """Decodes the clip once at 5 fps into 48x64 grey frames (milliseconds of work per clip)."""
    completed = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-i", str(video_path),
         "-vf", f"fps={ANALYSIS_FRAMES_PER_SECOND},scale={ANALYSIS_WIDTH}:{ANALYSIS_HEIGHT},format=gray",
         "-f", "rawvideo", "-"],
        capture_output=True,
    )  # fmt: skip
    if completed.returncode != 0:
        raise FfmpegFailed(completed.stderr.decode(errors="replace")[-2000:])
    frame_size = ANALYSIS_WIDTH * ANALYSIS_HEIGHT
    frame_count = len(completed.stdout) // frame_size
    return numpy.frombuffer(completed.stdout[: frame_count * frame_size], dtype=numpy.uint8).reshape(
        frame_count, ANALYSIS_HEIGHT, ANALYSIS_WIDTH
    ).astype(numpy.float32)


def best_window(frames: numpy.ndarray, clip_duration: float, window_seconds: float) -> Highlight:
    if clip_duration <= window_seconds or len(frames) < 3:
        return Highlight(0.0, min(window_seconds, clip_duration), 0.0)
    motion = numpy.abs(numpy.diff(frames, axis=0)).mean(axis=(1, 2))
    motion = numpy.minimum(motion, numpy.percentile(motion, 90))
    brightness = frames.mean(axis=(1, 2))[1:]
    usefulness = motion - numpy.where(brightness < DARK_LUMA, motion.max() + 1.0, 0.0)

    window_frames = max(1, round(window_seconds * ANALYSIS_FRAMES_PER_SECOND))
    earliest = EDGE_SKIP_SECONDS if clip_duration >= window_seconds + 2 * EDGE_SKIP_SECONDS else 0.0
    latest = clip_duration - window_seconds - earliest
    best_start, best_score = earliest, -numpy.inf
    for first_frame in range(0, max(1, len(usefulness) - window_frames + 1)):
        start = first_frame / ANALYSIS_FRAMES_PER_SECOND
        if start < earliest or start > latest:
            continue
        score = float(usefulness[first_frame : first_frame + window_frames].mean())
        if score > best_score:
            best_start, best_score = start, score
    return Highlight(round(best_start, 2), window_seconds, round(max(best_score, 0.0), 2))


def pick_highlight(video_path: Path, window_seconds: float = 3.0) -> Highlight:
    return best_window(grey_frames(video_path), probe_duration_seconds(video_path), window_seconds)
