"""Regression tests for issues found in code review."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from documenteveryday.domain import ClipCopy, ClipPlan, TranscribedWord, Transcript
from documenteveryday.llm.claude_gateway import ClaudeOutputUnusable, ClaudeRefused
from documenteveryday.pipeline.batch_workspace import BatchWorkspace
from documenteveryday.pipeline.job_runner import BatchJobRunner
from documenteveryday.qa.clip_checks import ClipUnderReview, find_framing_problems
from documenteveryday.storage.repositories import AiDecision
from documenteveryday.transcript_files import save_transcript
from documenteveryday.voiceover.voiceover_provider import NaturalNarration
from tests.fake_claude import fake_response
from tests.test_claude_gateway import make_gateway
from tests.test_repositories import make_repositories


def test_refused_calls_are_logged_with_their_cost():
    gateway, _, recorded = make_gateway(lambda request: fake_response("", stop_reason="refusal"))
    with pytest.raises(ClaudeRefused):
        gateway.request_text(purpose="write_copy", system="s", prompt="p", max_tokens=10, effort="low", clip_id=4)
    assert recorded[0].purpose == "write_copy" and recorded[0].cost_dollars > 0
    assert recorded[0].decision["error"].startswith("refused")


@pytest.mark.parametrize("response", [fake_response(""), fake_response("half a prof", stop_reason="max_tokens")])
def test_empty_or_cut_off_text_is_unusable_so_the_old_voice_profile_survives(response):
    gateway, _, recorded = make_gateway(lambda request: response)
    with pytest.raises(ClaudeOutputUnusable):
        gateway.request_text(purpose="refresh_voice_profile", system="s", prompt="p", max_tokens=10, effort="low")
    assert "error" in recorded[0].decision


def test_rerun_detaches_old_clip_decisions_so_reused_ids_start_clean(tmp_path):
    repositories = make_repositories(tmp_path)
    batch_id = repositories.batches.create()
    source_video_id = repositories.source_videos.add(batch_id, "a.mov", "/a.mov")
    old_clip_id = repositories.clips.create(batch_id, ClipPlan(source_video_id, 0, 1, 0, 20))
    repositories.ai_decisions.record(AiDecision(batch_id, old_clip_id, "write_copy", "m", 1, 1, 0.01, {}))
    repositories.clips.delete_for_batch(batch_id)
    new_clip_id = repositories.clips.create(batch_id, ClipPlan(source_video_id, 5, 9, 30, 50))
    [decision] = repositories.ai_decisions.for_batch(batch_id)
    assert new_clip_id == old_clip_id  # SQLite really does reuse the id
    assert decision["clip_id"] is None and decision["purpose"] == "write_copy (interrupted run)"
    assert repositories.ai_decisions.total_cost_for_batch(batch_id) == 0.01


def test_corrupt_transcript_cache_is_transcribed_again(tmp_path):
    from documenteveryday.pipeline.batch_pipeline import BatchPipeline
    from tests.pipeline_fakes import FakeTranscriber

    workspace = BatchWorkspace(tmp_path, 1)
    workspace.transcript_path(3).parent.mkdir(parents=True)
    workspace.transcript_path(3).write_text('{"source_video_id": 3, "words": [')
    transcriber = FakeTranscriber()
    pipeline = BatchPipeline.__new__(BatchPipeline)
    pipeline.transcriber = transcriber
    transcript = pipeline.cached_transcript(workspace, 3, Path("evening.mov"))
    assert transcript.words and transcriber.transcribed_paths == [Path("evening.mov")]


def test_transcript_cache_is_written_atomically(tmp_path):
    transcript_path = tmp_path / "t.json"
    save_transcript(Transcript(1, (TranscribedWord("hi.", 0, 1),)), transcript_path)
    assert transcript_path.exists() and not (tmp_path / "t.json.partial").exists()


def test_framing_check_reports_an_unreadable_render_instead_of_crashing(tmp_path):
    clip = ClipUnderReview(ClipPlan(1, 0, 0, 0, 1), (TranscribedWord("hi.", 0, 1),), (), tmp_path / "missing.mp4")
    [problem] = find_framing_problems(clip)
    assert problem.code == "BAD_FRAMING" and "Could not inspect" in problem.detail


@pytest.mark.ffmpeg
def test_one_clip_failing_to_render_does_not_fail_the_batch(tmp_path):
    from documenteveryday.pipeline.clip_workflow import ClipJob, ClipWorkflow

    repositories = make_repositories(tmp_path)
    batch_id = repositories.batches.create()
    source_video_id = repositories.source_videos.add(batch_id, "gone.mov", str(tmp_path / "gone.mov"))
    words = tuple(TranscribedWord(f"w{index}.", index, index + 0.5) for index in range(30))
    working_ai = SimpleNamespace(
        copywriter=SimpleNamespace(write=lambda plan, text, clip_id: ClipCopy("hook", "title", "caption", ())),
        translator=SimpleNamespace(translate=lambda cues, context, clip_id: cues),
        qa_agent=None,
    )
    workflow = ClipWorkflow(repositories, working_ai, NaturalNarration(), video_encoder="libx264")
    job = ClipJob(batch_id, ClipPlan(source_video_id, 0, 20, 0, 20.5), tmp_path / "gone.mov",
                  Transcript(source_video_id, words), tmp_path / "clips")  # fmt: skip
    assert workflow.run(job) is None
    [clip] = repositories.clips.for_batch(batch_id)
    assert clip["qa_status"] == "render_failed" and not clip["video_path"]
    assert clip["qa_summary"].startswith("FfmpegFailed")


def test_runner_keeps_working_when_housekeeping_fails():
    processed = []

    def failing_housekeeping():
        raise PermissionError("disk says no")

    runner = BatchJobRunner(processed.append, after_each_batch=failing_housekeeping)
    runner.start()
    for batch_id in (1, 2):
        runner.enqueue(batch_id)
    runner.pending_batch_ids.join()
    assert processed == [1, 2]
