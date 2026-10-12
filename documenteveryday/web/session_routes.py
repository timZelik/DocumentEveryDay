"""Signing in: trade the secret token for a long-lived HttpOnly cookie, so it never sits in a URL."""

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from documenteveryday.web.authentication import ONE_YEAR_SECONDS, TOKEN_COOKIE_NAME, token_matches
from documenteveryday.web.static_pages import static_page


class SessionRequest(BaseModel):
    token: str


def build_session_router(access_token: str) -> APIRouter:
    router = APIRouter()

    @router.get("/login")
    def login_page():
        return static_page("login.html")

    @router.post("/api/session")
    def create_session(session_request: SessionRequest, response: Response) -> dict:
        if not token_matches(session_request.token, access_token):
            raise HTTPException(status_code=401, detail="Wrong token.")
        response.set_cookie(
            TOKEN_COOKIE_NAME, session_request.token, max_age=ONE_YEAR_SECONDS,
            httponly=True, secure=True, samesite="lax",
        )  # fmt: skip
        return {"signed_in": True}

    return router
