from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from documenteveryday.maintenance.raw_footage_retention import delete_expired_raw_footage
from documenteveryday.notifications.ntfy_notifier import NtfyNotifier
from documenteveryday.pipeline.job_runner import BatchJobRunner
from documenteveryday.web.app import create_app
from tests.test_repositories import make_repositories
from tests.test_review_web import ACCESS_TOKEN, sign_in


def make_client(tmp_path):
    repositories = make_repositories(tmp_path)
    enqueued = []
    client = TestClient(create_app(repositories, ACCESS_TOKEN, tmp_path / "data", enqueued.append))
    sign_in(client)
    return client, repositories, enqueued


def test_upload_flow_streams_videos_and_queues_the_batch(tmp_path):
    client, repositories, enqueued = make_client(tmp_path)
    batch_id = client.post("/api/batches").json()["batch_id"]
    response = client.put(f"/api/batches/{batch_id}/videos?filename=IMG_0042.MOV", content=b"video-bytes")
    assert response.status_code == 200 and response.json()["bytes"] == 11
    [source_video] = repositories.source_videos.for_batch(batch_id)
    assert source_video["original_filename"] == "IMG_0042.MOV"
    assert Path(source_video["stored_path"]).read_bytes() == b"video-bytes"
    assert Path(source_video["stored_path"]).suffix == ".mov"
    started = client.post(f"/api/batches/{batch_id}/start")
    assert started.json()["status"] == "queued" and enqueued == [batch_id]
    assert client.post(f"/api/batches/{batch_id}/start").status_code == 409
    assert client.put(f"/api/batches/{batch_id}/videos?filename=late.mov", content=b"x").status_code == 409


def test_upload_rejects_non_video_names_and_path_tricks(tmp_path):
    client, repositories, _ = make_client(tmp_path)
    batch_id = client.post("/api/batches").json()["batch_id"]
    assert client.put(f"/api/batches/{batch_id}/videos?filename=run.sh", content=b"x").status_code == 415
    response = client.put(f"/api/batches/{batch_id}/videos?filename=../../evil.mov", content=b"x")
    [source_video] = repositories.source_videos.for_batch(batch_id)
    assert response.status_code == 200 and source_video["original_filename"] == "evil.mov"
    assert Path(source_video["stored_path"]).parent == tmp_path / "data" / "batches" / str(batch_id) / "uploads"


def test_starting_an_empty_batch_is_refused(tmp_path):
    client, _, enqueued = make_client(tmp_path)
    batch_id = client.post("/api/batches").json()["batch_id"]
    assert client.post(f"/api/batches/{batch_id}/start").status_code == 400 and enqueued == []


def test_upload_api_requires_the_token(tmp_path):
    repositories = make_repositories(tmp_path)
    client = TestClient(create_app(repositories, ACCESS_TOKEN, tmp_path, lambda batch_id: None))
    assert client.post("/api/batches").status_code == 401
    assert client.get("/upload", follow_redirects=False).status_code == 303


def test_retention_deletes_only_old_uploaded_footage(tmp_path):
    repositories = make_repositories(tmp_path)
    batch_id = repositories.batches.create()
    old_upload, my_own_file = tmp_path / "old.mov", tmp_path / "mine.mov"
    old_upload.write_bytes(b"x")
    my_own_file.write_bytes(b"x")
    repositories.source_videos.add(batch_id, "old.mov", str(old_upload), owned_by_pipeline=True)
    repositories.source_videos.add(batch_id, "mine.mov", str(my_own_file), owned_by_pipeline=False)
    assert delete_expired_raw_footage(repositories, 5) == 0
    assert delete_expired_raw_footage(repositories, 5, now=datetime.now(UTC) + timedelta(days=6)) == 1
    assert not old_upload.exists() and my_own_file.exists()


def test_runner_survives_a_crashing_batch_and_runs_cleanup_each_time():
    processed, cleanups = [], []

    def process(batch_id):
        processed.append(batch_id)
        if batch_id == 1:
            raise RuntimeError("boom")

    runner = BatchJobRunner(process, after_each_batch=lambda: cleanups.append(True))
    runner.start()
    runner.enqueue(1)
    runner.enqueue(2)
    runner.pending_batch_ids.join()
    assert processed == [1, 2] and len(cleanups) == 2


def test_ntfy_message_links_to_review_without_the_token(monkeypatch):
    sent = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *exception_info):
            return False

    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout: sent.append(request) or FakeResponse())
    NtfyNotifier("https://ntfy.sh/", "secret-topic", "https://mac.tailnet.ts.net").batch_ready(4, 7, 0.0213)
    [request] = sent
    assert request.full_url == "https://ntfy.sh/secret-topic"
    assert request.get_header("Click") == "https://mac.tailnet.ts.net/review/4"
    assert request.data == b"7 clips to swipe \xc2\xb7 AI cost $0.0213"
