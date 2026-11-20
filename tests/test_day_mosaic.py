import subprocess
from dataclasses import replace

import numpy
import pytest

from documenteveryday.day.auto_labels import parse_labels
from documenteveryday.day.day_plan import DayClip, DayPlan, load_plan, merge_plans, save_plan
from documenteveryday.day.day_planner import plan_day
from documenteveryday.day.highlight_picker import best_window
from documenteveryday.day.mosaic_layout import grid_tiles
from documenteveryday.day.mosaic_renderer import render_day_mosaic
from documenteveryday.media.ffmpeg_tools import probe_duration_seconds, probe_video_dimensions


@pytest.mark.parametrize("count", [1, 2, 5, 8, 12, 13, 20])
def test_grid_has_one_tile_per_clip_inside_the_area(count):
    tiles = grid_tiles(count, 1080, 1440, top=200)
    assert len(tiles) == count
    for tile in tiles:
        assert tile.width % 2 == 0 and tile.height % 2 == 0
        assert tile.x >= 0 and tile.x + tile.width <= 1080
        assert tile.y >= 200 and tile.y + tile.height <= 1640


def test_twelve_clips_make_a_puzzle_not_a_strip():
    columns = {tile.x for tile in grid_tiles(12, 1080, 1440)}
    assert 3 <= len(columns) <= 4


def test_highlight_prefers_motion_and_skips_dark_and_edges():
    frames = numpy.zeros((50, 64, 48), dtype=numpy.float32) + 100  # 10s at 5 fps, still
    frames[30:45] = numpy.random.default_rng(0).uniform(50, 200, (15, 64, 48))  # action from 6s to 9s
    highlight = best_window(frames, clip_duration=10.0, window_seconds=3.0)
    assert 5.4 <= highlight.start_seconds <= 6.4


def test_short_clip_plays_whole():
    assert best_window(numpy.zeros((10, 64, 48), dtype=numpy.float32), 2.0, 3.0).duration_seconds == 2.0


def test_plan_round_trips_and_keeps_my_edits(tmp_path):
    plan = DayPlan(title='Day "1"', stats="5 km", clips=(DayClip("a.mov", 1.5, label="Run", detail="5 km"),))
    save_plan(plan, tmp_path)
    assert load_plan(tmp_path) == plan
    fresh = DayPlan(title="x", clips=(DayClip("a.mov", 9.0), DayClip("b.mov", 2.0)))
    merged = merge_plans(plan, fresh)
    assert merged.title == 'Day "1"' and merged.clips[0].label == "Run" and merged.clips[0].start == 1.5
    assert merged.clips[1].file == "b.mov"


def test_parse_labels_pads_and_trims():
    assert parse_labels('Sure: ["Ran", "Folded laundry"]', 3) == ["Ran", "Folded laundry", ""]
    assert parse_labels('[] then ["A", "B"] and ["C"]', 2) == ["A", "B"]
    assert parse_labels("no idea", 2) == ["", ""]


@pytest.mark.ffmpeg
def test_plan_and_render_a_small_day(tmp_path):
    for index, size in enumerate(["720x1280", "1440x1920", "1280x720"]):
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"testsrc2=size={size}:rate=30:duration=5",
             "-c:v", "libx264", "-preset", "ultrafast", str(tmp_path / f"clip{index}.mp4")],
            check=True,
        )  # fmt: skip
    plan = plan_day(tmp_path, "Test day", labeler=lambda clips, folder: ["Ran"] * len(clips))
    assert [clip.label for clip in plan.clips] == ["Ran", "Ran", "Ran"]
    plan = replace(plan, clips=(*plan.clips[:2], replace(plan.clips[2], skip=True)))
    output = render_day_mosaic(plan, tmp_path, tmp_path / "day.mp4", "libx264")
    assert probe_video_dimensions(output).width == 1080
    assert probe_duration_seconds(output) == pytest.approx(6.0, abs=0.3)
