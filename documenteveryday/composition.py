"""Wires concrete pieces together from Settings. The only module that knows about every other one."""

import logging

from documenteveryday.config import Settings
from documenteveryday.maintenance.raw_footage_retention import delete_expired_raw_footage
from documenteveryday.notifications.notifier import LoggingNotifier, Notifier
from documenteveryday.notifications.ntfy_notifier import NtfyNotifier
from documenteveryday.pipeline.batch_pipeline import BatchPipeline
from documenteveryday.pipeline.job_runner import BatchJobRunner
from documenteveryday.storage.database import Database
from documenteveryday.storage.repositories import Repositories
from documenteveryday.transcription.transcriber import FasterWhisperTranscriber
from documenteveryday.web.app import create_app

INTERRUPTED_BATCH_STATUSES = ("queued", "processing")

logger = logging.getLogger(__name__)


def build_repositories(settings: Settings) -> Repositories:
    return Repositories.for_database(Database(settings.database_path))


def build_claude_client():
    import anthropic

    return anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment; never hard-code it


def build_notifier(settings: Settings) -> Notifier:
    if not settings.ntfy_topic:
        return LoggingNotifier()
    return NtfyNotifier(settings.ntfy_server, settings.ntfy_topic, settings.public_base_url)


def build_pipeline(settings: Settings, repositories: Repositories, notifier: Notifier | None = None) -> BatchPipeline:
    return BatchPipeline(
        settings=settings,
        repositories=repositories,
        transcriber=FasterWhisperTranscriber(settings.whisper_model),
        claude_client=build_claude_client(),
        notifier=notifier or LoggingNotifier(),
    )


def build_server(settings: Settings):
    """The app plus a started background runner, with batches a restart interrupted put back in line."""
    repositories = build_repositories(settings)
    pipeline = build_pipeline(settings, repositories, build_notifier(settings))

    def clean_up_old_footage() -> None:
        try:
            delete_expired_raw_footage(repositories, settings.raw_footage_retention_days)
        except Exception:  # housekeeping must never stop the server from starting or processing
            logger.exception("Raw footage cleanup failed")

    runner = BatchJobRunner(pipeline.run, after_each_batch=clean_up_old_footage)
    clean_up_old_footage()
    for batch in repositories.batches.with_status(*INTERRUPTED_BATCH_STATUSES):
        runner.enqueue(batch["id"])
    runner.start()
    return create_app(repositories, settings.access_token, settings.data_directory, runner.enqueue)
