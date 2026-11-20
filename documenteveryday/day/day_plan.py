"""The day's edit as a small TOML file (day.toml) next to the clips: generated, then hand-editable.

Re-planning keeps anything you typed (labels, starts, skips); only new clips get fresh picks.
"""

import json
import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path

PLAN_FILENAME = "day.toml"
VIDEO_SUFFIXES = {".mov", ".mp4", ".m4v"}


@dataclass(frozen=True)
class DayClip:
    file: str
    start: float
    seconds: float = 3.0
    label: str = ""
    detail: str = ""  # a second line on the tile, e.g. Strava numbers on the run clip
    skip: bool = False


@dataclass(frozen=True)
class DayPlan:
    title: str
    stats: str = ""  # shown big at the end, e.g. "Run 5.2 km · 28:14 · 5:26/km"
    clips: tuple[DayClip, ...] = field(default_factory=tuple)

    @property
    def shown_clips(self) -> tuple[DayClip, ...]:
        return tuple(clip for clip in self.clips if not clip.skip)


def toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)  # a JSON string is a valid TOML basic string


def render_plan_toml(plan: DayPlan) -> str:
    lines = [
        "# Edit freely, then run render-day. Set skip = true to drop a clip; change start to re-pick its moment.",
        f"title = {toml_string(plan.title)}",
        f"stats = {toml_string(plan.stats)}",
    ]
    for clip in plan.clips:
        lines += [
            "",
            "[[clips]]",
            f"file = {toml_string(clip.file)}",
            f"label = {toml_string(clip.label)}",
            f"detail = {toml_string(clip.detail)}",
            f"start = {clip.start}",
            f"seconds = {clip.seconds}",
            f"skip = {'true' if clip.skip else 'false'}",
        ]
    return "\n".join(lines) + "\n"


def save_plan(plan: DayPlan, day_directory: Path) -> Path:
    path = day_directory / PLAN_FILENAME
    path.write_text(render_plan_toml(plan), encoding="utf-8")
    return path


def load_plan(day_directory: Path) -> DayPlan | None:
    path = day_directory / PLAN_FILENAME
    if not path.exists():
        return None
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    clips = tuple(
        DayClip(
            file=entry["file"], start=float(entry.get("start", 0.0)), seconds=float(entry.get("seconds", 3.0)),
            label=entry.get("label", ""), detail=entry.get("detail", ""), skip=bool(entry.get("skip", False)),
        )  # fmt: skip
        for entry in data.get("clips", [])
    )
    return DayPlan(title=data.get("title", ""), stats=data.get("stats", ""), clips=clips)


def video_files(day_directory: Path) -> list[Path]:
    return [
        path for path in day_directory.iterdir()
        if path.suffix.lower() in VIDEO_SUFFIXES and not path.name.startswith(("day", "."))
    ]  # fmt: skip


def merge_plans(previous: DayPlan | None, fresh: DayPlan) -> DayPlan:
    """Your edits win; clips that disappeared from the folder drop out."""
    if previous is None:
        return fresh
    previous_by_file = {clip.file: clip for clip in previous.clips}
    merged = tuple(previous_by_file.get(clip.file, clip) for clip in fresh.clips)
    return replace(fresh, title=previous.title or fresh.title, stats=previous.stats or fresh.stats, clips=merged)
