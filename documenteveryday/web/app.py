"""Assembles the web app from its routers. Everything it needs is passed in, so tests can fake it."""

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from documenteveryday.storage.repositories import Repositories
from documenteveryday.web.authentication import require_access_token
from documenteveryday.web.review_routes import build_review_router
from documenteveryday.web.session_routes import build_session_router
from documenteveryday.web.static_pages import STATIC_DIRECTORY


def create_app(repositories: Repositories, access_token: str) -> FastAPI:
    if not access_token:
        raise ValueError("Set DOCUMENTEVERYDAY_ACCESS_TOKEN before serving the app.")
    guard = require_access_token(access_token)
    app = FastAPI(title="DocumentEveryday", docs_url=None, redoc_url=None, openapi_url=None)
    app.mount("/static", StaticFiles(directory=STATIC_DIRECTORY), name="static")
    app.include_router(build_session_router(access_token))
    app.include_router(build_review_router(repositories, access_token, guard))

    @app.get("/")
    def home():
        return RedirectResponse("/review", status_code=303)

    return app
