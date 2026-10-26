import pytest

from documenteveryday.domain import CaptionCue
from documenteveryday.media.ffmpeg_tools import probe_duration_seconds, probe_video_dimensions
from documenteveryday.production.clip_production import ClipProductionRequest, produce_clip


@pytest.mark.ffmpeg
def test_landscape_source_becomes_vertical_clip_with_burned_captions(synthetic_landscape_video, tmp_path):
    clip_path = produce_clip(
        ClipProductionRequest(
            source_path=synthetic_landscape_video,
            start_seconds=5.0,
            end_seconds=21.0,
            cues=[CaptionCue(0.0, 2.0, "hello there"), CaptionCue(2.0, 4.0, "ازيك", True, "How are you")],
            hook_line="I finally hit a new PR",
            output_directory=tmp_path / "folder with: odd 'chars'",
            clip_name="clip_1",
        )
    )
    dimensions = probe_video_dimensions(clip_path)
    assert (dimensions.width, dimensions.height) == (1080, 1920)
    assert probe_duration_seconds(clip_path) == pytest.approx(16.0, abs=0.2)
