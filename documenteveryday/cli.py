"""Command line entry point: `python -m documenteveryday <command>`."""

import argparse
import logging
from datetime import date
from pathlib import Path

from documenteveryday.captions.caption_cues import build_caption_cues
from documenteveryday.composition import build_pipeline, build_repositories, build_server
from documenteveryday.config import Settings
from documenteveryday.maintenance.raw_footage_retention import delete_expired_raw_footage
from documenteveryday.production.clip_production import ClipProductionRequest, produce_clip
from documenteveryday.review_seeding import seed_review_batch
from documenteveryday.selection.word_boundary_window import (
    cut_points_for_word_range,
    fit_word_range_to_duration,
    word_range_covering,
)
from documenteveryday.transcript_files import load_transcript, save_transcript
from documenteveryday.transcription.transcriber import FasterWhisperTranscriber


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

    uvicorn.run(build_server(Settings.from_environment()), host=arguments.host, port=arguments.port)


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


def transcribe_command(arguments: argparse.Namespace) -> None:
    transcript = FasterWhisperTranscriber(arguments.model).transcribe(arguments.video, source_video_id=0)
    save_transcript(transcript, arguments.output)
    arabic_word_count = sum(word.is_arabic for word in transcript.words)
    print(f"{len(transcript.words)} words ({arabic_word_count} in Arabic script) -> {arguments.output}")


def add_transcribe_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("transcribe", help="Transcribe one video to timed words (free, local).")
    parser.add_argument("video", type=Path)
    parser.add_argument("--output", type=Path, default=Path("transcript.json"))
    parser.add_argument("--model", default="small", help="faster-whisper model size.")
    parser.set_defaults(handler=transcribe_command)


def process_command(arguments: argparse.Namespace) -> None:
    """Runs the whole pipeline on local files, without the web app. Your originals are never deleted."""
    settings = Settings.from_environment()
    repositories = build_repositories(settings)
    batch_id = repositories.batches.create()
    for video in arguments.videos:
        repositories.source_videos.add(batch_id, video.name, str(video.resolve()), owned_by_pipeline=False)
    build_pipeline(settings, repositories).run(batch_id)
    batch = repositories.batches.get(batch_id)
    print(f"Batch {batch_id} {batch['status']}: {batch['status_detail']}")
    print(f"AI cost ${batch['total_cost_dollars']:.4f}. Review: {settings.public_base_url}/review/{batch_id}")


def add_process_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("process", help="Run the full pipeline on local videos.")
    parser.add_argument("videos", type=Path, nargs="+")
    parser.set_defaults(handler=process_command)


def cleanup_command(arguments: argparse.Namespace) -> None:
    settings = Settings.from_environment()
    deleted_count = delete_expired_raw_footage(build_repositories(settings), settings.raw_footage_retention_days)
    print(f"Deleted {deleted_count} raw videos older than {settings.raw_footage_retention_days} days.")


def add_cleanup_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("cleanup", help="Delete uploaded raw footage past its retention period.")
    parser.set_defaults(handler=cleanup_command)


def day_directory_for(arguments: argparse.Namespace, settings: Settings) -> Path:
    if getattr(arguments, "folder", None):
        return arguments.folder
    return settings.data_directory / "days" / arguments.date.isoformat()


def default_title(day: date) -> str:
    return day.strftime("%A · %b ") + str(day.day)


def claude_labeler(settings: Settings):
    import anthropic

    from documenteveryday.day.auto_labels import label_clips

    client = anthropic.Anthropic()

    def labeler(clips, day_directory):
        labels, usage = label_clips(clips, day_directory, client, settings.claude_model)
        print(f"Labelled {len(clips)} clips with {settings.claude_model}: {usage}")
        return labels

    return labeler


def make_day_command(arguments: argparse.Namespace) -> None:
    """Collect (Mac) -> plan (free motion picks, optional Haiku labels) -> render the mosaic."""
    from documenteveryday.day.day_plan import load_plan
    from documenteveryday.day.day_planner import plan_day
    from documenteveryday.day.mosaic_renderer import render_day_mosaic
    from documenteveryday.day.photos_collector import collect_day_videos, save_to_photos

    settings = Settings.from_environment()
    folder = day_directory_for(arguments, settings)
    if arguments.collect:
        collect_day_videos(arguments.date, folder, arguments.album)
    if not folder.is_dir():
        raise SystemExit(f"No folder {folder}: put the day's clips there, or pass --collect on the Mac.")
    if arguments.command_step in ("plan", "make"):
        labeler = claude_labeler(settings) if arguments.auto_label else None
        plan = plan_day(folder, arguments.title or default_title(arguments.date), arguments.seconds, labeler)
        print(f"Planned {len(plan.shown_clips)} clips -> {folder / 'day.toml'} (edit labels, stats, starts)")
    if arguments.command_step in ("render", "make"):
        plan = load_plan(folder)
        if plan is None:
            raise SystemExit("No day.toml yet: run plan-day first.")
        output = render_day_mosaic(
            plan, folder, folder / "day.mp4", settings.video_encoder, arguments.music, arguments.length
        )
        print(f"Rendered {output}")
        if arguments.to_photos:
            save_to_photos(output)
            print("Saved to Photos (album DocumentEveryDay); iCloud will put it on your iPhone.")


def add_day_parsers(subparsers: argparse._SubParsersAction) -> None:
    for step, help_text in (
        ("plan", "Order the day's clips and pick ~3s of each (free), writing day.toml."),
        ("render", "Render day.toml into the day's mosaic video, day.mp4."),
        ("make", "Plan and render in one go."),
    ):
        parser = subparsers.add_parser(f"{step}-day", help=help_text)
        parser.add_argument("folder", type=Path, nargs="?", help="Folder of clips (default data/days/<date>).")
        parser.add_argument("--date", type=date.fromisoformat, default=date.today(), help="YYYY-MM-DD")
        parser.add_argument("--title", default="", help="Defaults to e.g. 'Thursday · Nov 20'.")
        parser.add_argument("--seconds", type=float, default=3.0, help="Seconds shown from each clip.")
        parser.add_argument("--auto-label", action="store_true", help="Name tiles with one cheap Haiku call.")
        parser.add_argument("--collect", action="store_true", help="Mac: first pull the date's videos from Photos.")
        parser.add_argument("--album", help="With --collect: only this Photos album.")
        parser.add_argument("--length", type=float, default=6.0, help="Video length in seconds.")
        parser.add_argument("--music", type=Path, help="Optional audio track; otherwise silent.")
        parser.add_argument("--to-photos", action="store_true", help="Mac: import day.mp4 into Photos.")
        parser.set_defaults(handler=make_day_command, command_step=step)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="documenteveryday", description=__doc__)
    subparsers = parser.add_subparsers(required=True)
    for add_parser in (
        add_cut_parser, add_transcribe_parser, add_process_parser, add_seed_review_parser, add_serve_parser,
        add_cleanup_parser, add_day_parsers,
    ):  # fmt: skip
        add_parser(subparsers)
    return parser


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    arguments = build_argument_parser().parse_args()
    arguments.handler(arguments)
