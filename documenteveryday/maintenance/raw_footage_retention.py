"""Deletes uploaded raw footage after N days so the Mac's disk doesn't fill up. Clips and logs are kept;
footage I processed from my own folders with `process` is never touched."""

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from documenteveryday.storage.repositories import Repositories

logger = logging.getLogger(__name__)


def delete_expired_raw_footage(repositories: Repositories, retention_days: int, now: datetime | None = None) -> int:
    cutoff_text = ((now or datetime.now(UTC)) - timedelta(days=retention_days)).isoformat(timespec="seconds")
    expired_videos = repositories.source_videos.owned_uploaded_before(cutoff_text)
    for video in expired_videos:
        Path(video["stored_path"]).unlink(missing_ok=True)
        repositories.source_videos.mark_deleted(video["id"])
        logger.info("Deleted raw footage %s (older than %s days)", video["original_filename"], retention_days)
    return len(expired_videos)
