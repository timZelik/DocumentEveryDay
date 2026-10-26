"""The review page, its data, clip video files, and approve/reject decisions."""

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from documenteveryday.storage.database import utc_now_text
from documenteveryday.storage.repositories import Repositories
from documenteveryday.web.request_files import extension_for_content_type, save_request_body
from documenteveryday.web.review_payload import build_review_payload
from documenteveryday.web.static_pages import guarded_static_page

VOICE_NOTE_EXTENSIONS = {"audio/mp4": ".m4a", "audio/x-m4a": ".m4a", "audio/webm": ".webm", "audio/ogg": ".ogg"}


class ReviewDecision(BaseModel):
    decision: Literal["approved", "rejected", "needs_review"]


def existing_or_404(record: dict | None, what: str) -> dict:
    if record is None:
        raise HTTPException(status_code=404, detail=f"No such {what}.")
    return record


def existing_file_or_404(path_text: str, what: str) -> Path:
    if not path_text or not Path(path_text).exists():
        raise HTTPException(status_code=404, detail=f"No {what} yet.")
    return Path(path_text)


def build_review_router(repositories: Repositories, access_token: str, guard, voice_notes_directory: Path) -> APIRouter:
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

    @router.put("/api/clips/{clip_id}/voice-note", dependencies=[Depends(guard)])
    async def upload_voice_note(clip_id: int, request: Request) -> dict:
        """The swipe-up note explaining why a clip needs another look."""
        existing_or_404(repositories.clips.get(clip_id), "clip")
        extension = extension_for_content_type(request.headers.get("content-type", ""), VOICE_NOTE_EXTENSIONS)
        voice_note_path = voice_notes_directory / f"clip_{clip_id}{extension}"
        await save_request_body(request, voice_note_path)
        repositories.clips.update(clip_id, voice_note_path=str(voice_note_path))
        return {"clip_id": clip_id, "voice_note_url": f"/media/voice-notes/{clip_id}"}

    @router.get("/media/clips/{clip_id}", dependencies=[Depends(guard)])
    def clip_video(clip_id: int) -> FileResponse:
        clip = existing_or_404(repositories.clips.get(clip_id), "clip")
        video_path = existing_file_or_404(clip["video_path"], "rendered video")
        return FileResponse(video_path, media_type="video/mp4", filename=f"documenteveryday_clip_{clip_id}.mp4")

    @router.get("/media/voice-notes/{clip_id}", dependencies=[Depends(guard)])
    def voice_note(clip_id: int) -> FileResponse:
        clip = existing_or_404(repositories.clips.get(clip_id), "clip")
        return FileResponse(existing_file_or_404(clip["voice_note_path"], "voice note"))

    return router
