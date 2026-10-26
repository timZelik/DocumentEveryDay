"""Streams a raw request body to disk without holding it in memory: multi-GB footage and small voice notes."""

from pathlib import Path

from fastapi import HTTPException, Request


async def save_request_body(request: Request, destination_path: Path) -> int:
    """Writes to a temporary name first, so a dropped upload never leaves a half file that looks complete."""
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    partial_path = destination_path.with_name(destination_path.name + ".partial")
    written_bytes = 0
    with partial_path.open("wb") as partial_file:
        async for chunk in request.stream():
            partial_file.write(chunk)
            written_bytes += len(chunk)
    if written_bytes == 0:
        partial_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="The upload was empty.")
    partial_path.replace(destination_path)
    return written_bytes


def extension_for_content_type(content_type: str, allowed_extensions: dict[str, str]) -> str:
    media_type = content_type.split(";")[0].strip().lower()
    if media_type not in allowed_extensions:
        raise HTTPException(status_code=415, detail=f"Unsupported type {media_type or '(none)'}.")
    return allowed_extensions[media_type]
