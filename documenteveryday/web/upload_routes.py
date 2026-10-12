"""The upload page and its API: create a batch, stream each video into it, then start processing."""

import uuid
from collections.abc import Callable
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request

from documenteveryday.pipeline.batch_workspace import BatchWorkspace
from documenteveryday.storage.repositories import Repositories
from documenteveryday.web.request_files import save_request_body
from documenteveryday.web.review_routes import existing_or_404
from documenteveryday.web.static_pages import guarded_static_page

ALLOWED_VIDEO_EXTENSIONS = {".mov", ".mp4", ".m4v"}


def video_extension(filename: str) -> str:
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_VIDEO_EXTENSIONS:
        raise HTTPException(status_code=415, detail=f"Upload .mov, .mp4 or .m4v files, not '{extension or filename}'.")
    return extension


def uploading_batch_or_409(repositories: Repositories, batch_id: int) -> dict:
    batch = existing_or_404(repositories.batches.get(batch_id), "batch")
    if batch["status"] != "uploading":
        raise HTTPException(status_code=409, detail=f"Batch {batch_id} is already {batch['status']}.")
    return batch


def build_upload_router(
    repositories: Repositories, access_token: str, guard, data_directory: Path, enqueue_batch: Callable[[int], None]
) -> APIRouter:
    router = APIRouter()

    @router.get("/upload")
    def upload_page(request: Request):
        return guarded_static_page(request, access_token, "upload.html")

    @router.post("/api/batches", dependencies=[Depends(guard)])
    def create_batch() -> dict:
        return {"batch_id": repositories.batches.create()}

    @router.put("/api/batches/{batch_id}/videos", dependencies=[Depends(guard)])
    async def upload_video(batch_id: int, filename: str, request: Request) -> dict:
        """The stored name is random; only the extension of my filename is trusted."""
        uploading_batch_or_409(repositories, batch_id)
        stored_path = BatchWorkspace(data_directory, batch_id).uploads_directory / (
            uuid.uuid4().hex + video_extension(filename)
        )
        written_bytes = await save_request_body(request, stored_path)
        source_video_id = repositories.source_videos.add(batch_id, Path(filename).name, str(stored_path))
        return {"source_video_id": source_video_id, "bytes": written_bytes}

    @router.post("/api/batches/{batch_id}/start", dependencies=[Depends(guard)])
    def start_batch(batch_id: int) -> dict:
        uploading_batch_or_409(repositories, batch_id)
        if not repositories.source_videos.for_batch(batch_id):
            raise HTTPException(status_code=400, detail="Upload at least one video first.")
        repositories.batches.set_status(batch_id, "queued", "Waiting to start")
        enqueue_batch(batch_id)
        return {"batch_id": batch_id, "status": "queued", "review_url": f"/review/{batch_id}"}

    return router
