"""Serves the hand-written HTML pages, sending signed-out visitors to the login page."""

from pathlib import Path

from fastapi import Request
from fastapi.responses import FileResponse, RedirectResponse

from documenteveryday.web.authentication import presented_token, token_matches

STATIC_DIRECTORY = Path(__file__).parent / "static"


def static_page(filename: str) -> FileResponse:
    return FileResponse(STATIC_DIRECTORY / filename, headers={"Cache-Control": "no-store"})


def guarded_static_page(request: Request, access_token: str, filename: str):
    if not token_matches(presented_token(request), access_token):
        return RedirectResponse(f"/login?next={request.url.path}", status_code=303)
    return static_page(filename)
