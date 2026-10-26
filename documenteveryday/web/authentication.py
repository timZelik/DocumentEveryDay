"""One shared secret token, no accounts. Accepted from an HttpOnly cookie or a Bearer header."""

import secrets

from fastapi import HTTPException, Request

TOKEN_COOKIE_NAME = "documenteveryday_token"
ONE_YEAR_SECONDS = 365 * 24 * 3600


def presented_token(request: Request) -> str:
    authorization_header = request.headers.get("authorization", "")
    bearer_token = authorization_header.removeprefix("Bearer ").strip() if authorization_header else ""
    return request.cookies.get(TOKEN_COOKIE_NAME, "") or bearer_token


def token_matches(candidate_token: str, access_token: str) -> bool:
    return bool(candidate_token) and secrets.compare_digest(candidate_token.encode(), access_token.encode())


def require_access_token(access_token: str):
    """Builds the FastAPI dependency that guards every API route and media file."""

    def dependency(request: Request) -> None:
        if not token_matches(presented_token(request), access_token):
            raise HTTPException(status_code=401, detail="Missing or wrong access token.")

    return dependency
