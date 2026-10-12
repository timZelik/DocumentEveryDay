"""Wires concrete pieces together from Settings. The only module that knows about every other one."""

from documenteveryday.config import Settings
from documenteveryday.notifications.notifier import LoggingNotifier, Notifier
from documenteveryday.pipeline.batch_pipeline import BatchPipeline
from documenteveryday.storage.database import Database
from documenteveryday.storage.repositories import Repositories
from documenteveryday.transcription.transcriber import FasterWhisperTranscriber
from documenteveryday.web.app import create_app


def build_repositories(settings: Settings) -> Repositories:
    return Repositories.for_database(Database(settings.database_path))


def build_claude_client():
    import anthropic

    return anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment; never hard-code it


def build_pipeline(settings: Settings, repositories: Repositories, notifier: Notifier | None = None) -> BatchPipeline:
    return BatchPipeline(
        settings=settings,
        repositories=repositories,
        transcriber=FasterWhisperTranscriber(settings.whisper_model),
        claude_client=build_claude_client(),
        notifier=notifier or LoggingNotifier(),
    )


def build_web_app(settings: Settings):
    return create_app(build_repositories(settings), settings.access_token, settings.data_directory)
