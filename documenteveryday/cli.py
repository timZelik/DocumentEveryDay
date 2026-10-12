"""Command line entry point: `python -m documenteveryday <command>`."""

import argparse
import logging
from pathlib import Path

from documenteveryday.captions.caption_cues import build_caption_cues
from documenteveryday.production.clip_production import ClipProductionRequest, produce_clip
from documenteveryday.selection.word_boundary_window import (
    cut_points_for_word_range,
    fit_word_range_to_duration,
    word_range_covering,
)
from documenteveryday.transcript_files import load_transcript


def cut_command(arguments: argparse.Namespace) -> None:
    """Stage 1 check: cut a 9:16 clip by hand, optionally snapped to words with captions burned in."""
    start_seconds, end_seconds, cues = arguments.start, arguments.end, []
    if arguments.transcript:
        words = load_transcript(arguments.transcript).words
        covered_range = word_range_covering(words, start_seconds, end_seconds)
        if covered_range is None:
            raise SystemExit("No words are spoken between --start and --end.")
        fitted_range = fit_word_range_to_duration(words, covered_range) or covered_range
        start_seconds, end_seconds = cut_points_for_word_range(words, fitted_range)
        cues = build_caption_cues(words, start_seconds, end_seconds)
    output_path = produce_clip(
        ClipProductionRequest(
            source_path=arguments.video,
            start_seconds=start_seconds,
            end_seconds=end_seconds,
            cues=cues,
            hook_line=arguments.hook,
            output_directory=arguments.output.parent,
            clip_name=arguments.output.stem,
            video_encoder=arguments.encoder,
        )
    )
    clip_duration = end_seconds - start_seconds
    print(f"Cut {start_seconds:.2f}s to {end_seconds:.2f}s ({clip_duration:.1f}s) -> {output_path}")


def add_cut_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("cut", help="Cut one 9:16 clip from a video.")
    parser.add_argument("video", type=Path)
    parser.add_argument("--start", type=float, required=True, help="Seconds into the video.")
    parser.add_argument("--end", type=float, required=True)
    parser.add_argument("--output", type=Path, default=Path("clip.mp4"))
    parser.add_argument(
        "--transcript", type=Path, help="Transcript JSON from `transcribe`, to snap to words."
    )
    parser.add_argument("--hook", default="", help="Optional hook line shown for the first seconds.")
    parser.add_argument("--encoder", default="libx264", choices=["libx264", "h264_videotoolbox"])
    parser.set_defaults(handler=cut_command)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="documenteveryday", description=__doc__)
    subparsers = parser.add_subparsers(required=True)
    add_cut_parser(subparsers)
    return parser


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    arguments = build_argument_parser().parse_args()
    arguments.handler(arguments)
