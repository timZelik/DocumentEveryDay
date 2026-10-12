import pytest
from fastapi.testclient import TestClient

from documenteveryday.domain import ClipPlan
from documenteveryday.storage.repositories import AiDecision
from documenteveryday.web.app import create_app
from tests.test_repositories import make_repositories

ACCESS_TOKEN = "correct-horse-battery-staple"


@pytest.fixture
def seeded(tmp_path):
    repositories = make_repositories(tmp_path)
    batch_id = repositories.batches.create()
    repositories.batches.set_status(batch_id, "ready")
    source_video_id = repositories.source_videos.add(batch_id, "evening.mov", "/tmp/evening.mov")
    clip_id = repositories.clips.create(batch_id, ClipPlan(source_video_id, 0, 5, 0.0, 20.0, pick_reason="PR set"))
    video_path = tmp_path / "clip.mp4"
    video_path.write_bytes(b"0123456789" * 100)
    repositories.clips.update(clip_id, video_path=str(video_path), post_caption="New PR", hashtags=("gym",))
    repositories.ai_decisions.record(AiDecision(batch_id, clip_id, "copywrite", "m", 10, 5, 0.001, {"ok": 1}))
    repositories.ai_decisions.record(AiDecision(batch_id, None, "score_moments", "m", 10, 5, 0.002, {}))
    repositories.batches.set_total_cost(batch_id, 0.003)
    client = TestClient(create_app(repositories, ACCESS_TOKEN, tmp_path))
    return client, repositories, batch_id, clip_id


def sign_in(client: TestClient) -> None:
    assert client.post("/api/session", json={"token": ACCESS_TOKEN}).status_code == 200
    client.cookies.set("documenteveryday_token", ACCESS_TOKEN)  # TestClient talks plain http; cookie is Secure


def test_api_and_media_reject_missing_or_wrong_token(seeded):
    client, _, batch_id, clip_id = seeded
    assert client.get(f"/api/batches/{batch_id}").status_code == 401
    assert client.get(f"/media/clips/{clip_id}", headers={"Authorization": "Bearer nope"}).status_code == 401
    assert client.post("/api/session", json={"token": "nope"}).status_code == 401


def test_signed_out_page_visit_redirects_to_login(seeded):
    client, *_ = seeded
    response = client.get("/review", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")


def test_payload_includes_clip_decisions_costs_and_clipboard_text(seeded):
    client, _, batch_id, clip_id = seeded
    sign_in(client)
    payload = client.get("/api/batches/latest").json()
    [clip] = payload["clips"]
    assert payload["total_cost_dollars"] == 0.003
    assert clip["clipboard_text"] == "New PR\n\n#gym"
    assert clip["ai_cost_dollars"] == 0.001
    assert [decision["purpose"] for decision in payload["batch_decisions"]] == ["score_moments"]
    assert "video_path" not in clip


def test_review_decision_is_saved(seeded):
    client, repositories, _, clip_id = seeded
    sign_in(client)
    assert client.post(f"/api/clips/{clip_id}/review", json={"decision": "approved"}).status_code == 200
    assert repositories.clips.get(clip_id)["review_status"] == "approved"
    assert client.post(f"/api/clips/{clip_id}/review", json={"decision": "maybe"}).status_code == 422


def test_clip_media_supports_range_requests_for_ios_video(seeded):
    client, _, _, clip_id = seeded
    sign_in(client)
    response = client.get(f"/media/clips/{clip_id}", headers={"Range": "bytes=0-9"})
    assert response.status_code == 206
    assert response.content == b"0123456789"


def test_app_refuses_to_start_without_a_token(tmp_path):
    with pytest.raises(ValueError):
        create_app(make_repositories(tmp_path), "", tmp_path)


def test_swipe_up_marks_needs_review_and_stores_a_playable_voice_note(seeded):
    client, repositories, _, clip_id = seeded
    sign_in(client)
    assert client.post(f"/api/clips/{clip_id}/review", json={"decision": "needs_review"}).status_code == 200
    upload = client.put(f"/api/clips/{clip_id}/voice-note", content=b"fake-m4a", headers={"Content-Type": "audio/mp4"})
    assert upload.status_code == 200
    [clip] = client.get("/api/batches/latest").json()["clips"]
    assert clip["review_status"] == "needs_review"
    assert client.get(clip["voice_note_url"]).content == b"fake-m4a"


def test_voice_note_rejects_non_audio_and_empty_uploads(seeded):
    client, _, _, clip_id = seeded
    sign_in(client)
    assert (
        client.put(f"/api/clips/{clip_id}/voice-note", content=b"x", headers={"Content-Type": "text/html"}).status_code
        == 415
    )
    assert (
        client.put(f"/api/clips/{clip_id}/voice-note", content=b"", headers={"Content-Type": "audio/mp4"}).status_code
        == 400
    )
