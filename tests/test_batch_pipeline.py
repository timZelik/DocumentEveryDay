import dataclasses

import pytest

from documenteveryday.config import Settings
from documenteveryday.media.ffmpeg_tools import probe_video_dimensions
from documenteveryday.notifications.notifier import LoggingNotifier
from documenteveryday.pipeline.batch_pipeline import BatchPipeline
from tests.fake_claude import FakeClaudeClient
from tests.pipeline_fakes import FakeTranscriber, analysis_routes
from tests.test_repositories import make_repositories


class RecordingNotifier(LoggingNotifier):
    def __init__(self):
        self.events = []

    def batch_ready(self, batch_id, clip_count, total_cost_dollars):
        self.events.append(("ready", batch_id, clip_count))

    def batch_failed(self, batch_id, reason):
        self.events.append(("failed", batch_id, reason))


def make_settings(tmp_path, **overrides) -> Settings:
    rule_path = tmp_path / "rule.md"
    rule_path.write_text("Keep EFFORT, RESULT, LESSON moments.")
    settings = Settings.from_environment()
    return dataclasses.replace(
        settings, data_directory=tmp_path / "data", rule_path=rule_path,
        voice_profile_path=tmp_path / "my_voice.md", **overrides,
    )  # fmt: skip


def run_batch(tmp_path, video_path, routes, **setting_overrides):
    repositories = make_repositories(tmp_path)
    batch_id = repositories.batches.create()
    repositories.source_videos.add(batch_id, "evening.mp4", str(video_path), owned_by_pipeline=False)
    notifier = RecordingNotifier()
    client = FakeClaudeClient(routes)
    settings = make_settings(tmp_path, **setting_overrides)
    BatchPipeline(settings, repositories, FakeTranscriber(), client, notifier).run(batch_id)
    return repositories, batch_id, notifier, client


@pytest.mark.ffmpeg
def test_pipeline_turns_footage_into_reviewable_clips_and_logs_cost(tmp_path, synthetic_landscape_video):
    repositories, batch_id, notifier, client = run_batch(tmp_path, synthetic_landscape_video, analysis_routes())
    batch = repositories.batches.get(batch_id)
    [clip] = repositories.clips.for_batch(batch_id)
    assert batch["status"] == "ready", batch["status_detail"]
    assert notifier.events == [("ready", batch_id, 1)]
    assert clip["tag"] == "training" and clip["score"] == 9 and clip["criteria"] == ["EFFORT", "LESSON"]
    assert 15 <= clip["end_seconds"] - clip["start_seconds"] <= 60
    dimensions = probe_video_dimensions(clip["video_path"])
    assert (dimensions.width, dimensions.height) == (1080, 1920)
    purposes = [decision["purpose"] for decision in repositories.ai_decisions.for_batch(batch_id)]
    assert {"classify_segments", "score_moments"} <= set(purposes)
    assert batch["total_cost_dollars"] == pytest.approx(repositories.ai_decisions.total_cost_for_batch(batch_id))
    assert all(request["model"] == "claude-haiku-5-5" for request in client.requests)


@pytest.mark.ffmpeg
def test_budget_too_small_fails_the_batch_before_spending(tmp_path, synthetic_landscape_video):
    repositories, batch_id, notifier, client = run_batch(
        tmp_path, synthetic_landscape_video, analysis_routes(), batch_budget_dollars=0.0000001
    )
    batch = repositories.batches.get(batch_id)
    assert batch["status"] == "failed" and "BatchBudgetExceeded" in batch["status_detail"]
    assert notifier.events[0][0] == "failed"
    assert client.requests == []
