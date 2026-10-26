from documenteveryday.domain import ClipPlan, GoodClipCriterion, SegmentTag
from documenteveryday.storage.database import Database
from documenteveryday.storage.repositories import AiDecision, Repositories


def make_repositories(tmp_path) -> Repositories:
    return Repositories.for_database(Database(tmp_path / "test.sqlite3"))


def test_clip_round_trip_decodes_json_lists(tmp_path):
    repositories = make_repositories(tmp_path)
    batch_id = repositories.batches.create()
    source_video_id = repositories.source_videos.add(batch_id, "evening.mov", "/tmp/evening.mov")
    plan = ClipPlan(source_video_id, 0, 10, 1.0, 20.0, SegmentTag.TRAINING, "lifting", 8,
                    (GoodClipCriterion.EFFORT,), "heavy set")  # fmt: skip
    clip_id = repositories.clips.create(batch_id, plan)
    repositories.clips.update(clip_id, hashtags=("gym", "pr"), qa_status="passed")
    clip = repositories.clips.get(clip_id)
    assert clip["criteria"] == ["EFFORT"]
    assert clip["hashtags"] == ["gym", "pr"]
    assert clip["qa_status"] == "passed"


def test_update_refuses_unknown_columns(tmp_path):
    repositories = make_repositories(tmp_path)
    try:
        repositories.clips.update(1, batch_id=5)
    except ValueError as error:
        assert "batch_id" in str(error)
    else:
        raise AssertionError("expected ValueError")


def test_ai_decisions_are_stored_with_their_decision_payload(tmp_path):
    repositories = make_repositories(tmp_path)
    batch_id = repositories.batches.create()
    repositories.ai_decisions.record(
        AiDecision(batch_id, None, "classify_segments", "claude-haiku-5-5", 100, 20, 0.00002, {"tags": 3})
    )
    [stored] = repositories.ai_decisions.for_batch(batch_id)
    assert stored["decision"] == {"tags": 3}
    assert stored["clip_id"] is None


def test_retention_query_only_returns_owned_undeleted_videos(tmp_path):
    repositories = make_repositories(tmp_path)
    batch_id = repositories.batches.create()
    owned_id = repositories.source_videos.add(batch_id, "a.mov", "/a.mov", owned_by_pipeline=True)
    repositories.source_videos.add(batch_id, "b.mov", "/b.mov", owned_by_pipeline=False)
    assert [video["id"] for video in repositories.source_videos.owned_uploaded_before("9999")] == [owned_id]
    repositories.source_videos.mark_deleted(owned_id)
    assert repositories.source_videos.owned_uploaded_before("9999") == []


def test_old_database_files_gain_new_columns(tmp_path):
    import sqlite3

    database_path = tmp_path / "old.sqlite3"
    connection = sqlite3.connect(database_path)
    connection.execute("CREATE TABLE clips (id INTEGER PRIMARY KEY, batch_id INTEGER)")
    connection.commit()
    connection.close()
    Database(database_path)
    columns = {row[1] for row in sqlite3.connect(database_path).execute("PRAGMA table_info(clips)")}
    assert "voice_note_path" in columns
