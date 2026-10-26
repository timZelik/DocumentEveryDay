"""Tells me when a batch is done. The Protocol keeps the pipeline unaware of ntfy."""

import logging
from typing import Protocol

logger = logging.getLogger(__name__)


class Notifier(Protocol):
    def batch_ready(self, batch_id: int, clip_count: int, total_cost_dollars: float) -> None: ...

    def batch_failed(self, batch_id: int, reason: str) -> None: ...


class LoggingNotifier:
    """Used when no ntfy topic is configured, e.g. on the command line."""

    def batch_ready(self, batch_id: int, clip_count: int, total_cost_dollars: float) -> None:
        logger.info("Batch %s ready: %s clips, AI cost $%.4f", batch_id, clip_count, total_cost_dollars)

    def batch_failed(self, batch_id: int, reason: str) -> None:
        logger.error("Batch %s failed: %s", batch_id, reason)
