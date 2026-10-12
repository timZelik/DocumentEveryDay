"""Wires concrete pieces together from Settings. The only module that knows about every other one."""

from documenteveryday.config import Settings
from documenteveryday.storage.database import Database
from documenteveryday.storage.repositories import Repositories
from documenteveryday.web.app import create_app


def build_repositories(settings: Settings) -> Repositories:
    return Repositories.for_database(Database(settings.database_path))


def build_web_app(settings: Settings):
    return create_app(build_repositories(settings), settings.access_token)
