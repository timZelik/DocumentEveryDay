"""The review page, its data, clip video files, and approve/reject decisions."""

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from documenteveryday.storage.database import utc_now_text
from documenteveryday.storage.repositories import Repositories
from documenteveryday.web.review_payload import build_review_payload
from documenteveryday.web.static_pages import guarded_static_page


class ReviewDecision(BaseModel):
    decision: Literal["approved", "rejected"]


def existing_or_404(record: dict | None, what: str) -> dict:
    if record is None:
        raise HTTPException(status_code=404, detail=f"No such {what}.")
    return record


def build_review_router(repositories: Repositories, access_token: str, guard) -> APIRouter:
    router = APIRouter()

    @router.get("/review")
    @router.get("/review/{batch_id}")
    def review_page(request: Request, batch_id: int | None = None):
        return guarded_static_page(request, access_token, "review.html")

    @router.get("/api/batches/latest", dependencies=[Depends(guard)])
    def latest_batch() -> dict:
        return build_review_payload(repositories, existing_or_404(repositories.batches.latest(), "batch"))

    @router.get("/api/batches/{batch_id}", dependencies=[Depends(guard)])
    def batch_by_id(batch_id: int) -> dict:
        return build_review_payload(repositories, existing_or_404(repositories.batches.get(batch_id), "batch"))

    @router.post("/api/clips/{clip_id}/review", dependencies=[Depends(guard)])
    def review_clip(clip_id: int, review_decision: ReviewDecision) -> dict:
        existing_or_404(repositories.clips.get(clip_id), "clip")
        repositories.clips.update(clip_id, review_status=review_decision.decision, reviewed_at=utc_now_text())
        return {"clip_id": clip_id, "review_status": review_decision.decision}

    @router.get("/media/clips/{clip_id}", dependencies=[Depends(guard)])
    def clip_video(clip_id: int) -> FileResponse:
        clip = existing_or_404(repositories.clips.get(clip_id), "clip")
        video_path = Path(clip["video_path"]) if clip["video_path"] else None
        if video_path is None or not video_path.exists():
            raise HTTPException(status_code=404, detail="Clip video is not rendered yet.")
        return FileResponse(video_path, media_type="video/mp4", filename=f"documenteveryday_clip_{clip_id}.mp4")

    return router
