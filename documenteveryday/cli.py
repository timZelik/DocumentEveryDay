"""Command line entry point: `python -m documenteveryday <command>`."""

import argparse
import logging
from pathlib import Path

from documenteveryday.captions.caption_cues import build_caption_cues
from documenteveryday.composition import build_repositories, build_web_app
from documenteveryday.config import Settings
from documenteveryday.production.clip_production import ClipProductionRequest, produce_clip
from documenteveryday.review_seeding import seed_review_batch
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
    parser.add_argument("--transcript", type=Path, help="Transcript JSON from `transcribe`, to snap to words.")
    parser.add_argument("--hook", default="", help="Optional hook line shown for the first seconds.")
    parser.add_argument("--encoder", default="libx264", choices=["libx264", "h264_videotoolbox"])
    parser.set_defaults(handler=cut_command)


def serve_command(arguments: argparse.Namespace) -> None:
    import uvicorn

    uvicorn.run(build_web_app(Settings.from_environment()), host=arguments.host, port=arguments.port)


def add_serve_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("serve", help="Serve the upload page, review page and API.")
    parser.add_argument("--host", default="127.0.0.1", help="Tailscale Serve proxies to localhost.")
    parser.add_argument("--port", type=int, default=8000)
    parser.set_defaults(handler=serve_command)


def seed_review_command(arguments: argparse.Namespace) -> None:
    settings = Settings.from_environment()
    batch_id = seed_review_batch(
        build_repositories(settings), arguments.video, settings.data_directory / "clips",
        arguments.clips, settings.video_encoder,
    )  # fmt: skip
    print(f"Seeded batch {batch_id}: open {settings.public_base_url}/review/{batch_id}")


def add_seed_review_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("seed-review", help="Fill the review page with plain cuts (no AI).")
    parser.add_argument("video", type=Path)
    parser.add_argument("--clips", type=int, default=5)
    parser.set_defaults(handler=seed_review_command)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="documenteveryday", description=__doc__)
    subparsers = parser.add_subparsers(required=True)
    for add_parser in (add_cut_parser, add_seed_review_parser, add_serve_parser):
        add_parser(subparsers)
    return parser


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    arguments = build_argument_parser().parse_args()
    arguments.handler(arguments)
