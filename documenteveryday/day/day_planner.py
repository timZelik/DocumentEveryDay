"""Builds (or refreshes) a day's plan: order clips by capture time, pick each one's best seconds, label."""

import logging
from dataclasses import replace
from pathlib import Path

from documenteveryday.day.capture_time import capture_timestamp
from documenteveryday.day.day_plan import DayClip, DayPlan, load_plan, merge_plans, save_plan, video_files
from documenteveryday.day.highlight_picker import pick_highlight

logger = logging.getLogger(__name__)


def plan_day(day_directory: Path, title: str, seconds_per_clip: float = 3.0, labeler=None) -> DayPlan:
    """labeler: optional callable(clips, day_directory) -> list[str] for clips that have no label yet."""
    previous = load_plan(day_directory)
    previous_files = {clip.file for clip in previous.clips} if previous else set()
    ordered = sorted(video_files(day_directory), key=capture_timestamp)
    fresh_clips = []
    for video in ordered:
        if video.name in previous_files:
            fresh_clips.append(DayClip(file=video.name, start=0.0))  # placeholder; merge keeps your version
            continue
        highlight = pick_highlight(video, seconds_per_clip)
        logger.info("%s: best %.1fs at %.1fs (motion %.1f)", video.name, highlight.duration_seconds,
                    highlight.start_seconds, highlight.motion_score)  # fmt: skip
        fresh_clips.append(DayClip(file=video.name, start=highlight.start_seconds, seconds=seconds_per_clip))
    plan = merge_plans(previous, DayPlan(title=title, clips=tuple(fresh_clips)))

    unlabeled = [clip for clip in plan.clips if not clip.label and not clip.skip]
    if labeler is not None and unlabeled:
        labels = dict(zip((clip.file for clip in unlabeled), labeler(unlabeled, day_directory), strict=True))
        plan = replace(plan, clips=tuple(replace(clip, label=labels.get(clip.file, clip.label)) for clip in plan.clips))
    save_plan(plan, day_directory)
    return plan
