"""Runs batches one at a time on a background thread, so uploads return instantly and the Mac's CPU is
never split between two encodes."""

import logging
import queue
import threading
from collections.abc import Callable

logger = logging.getLogger(__name__)


class BatchJobRunner:
    def __init__(self, process_batch: Callable[[int], None], after_each_batch: Callable[[], None] = lambda: None):
        self.process_batch = process_batch
        self.after_each_batch = after_each_batch
        self.pending_batch_ids: queue.Queue[int] = queue.Queue()

    def start(self) -> None:
        threading.Thread(target=self.work_forever, name="batch-runner", daemon=True).start()

    def enqueue(self, batch_id: int) -> None:
        self.pending_batch_ids.put(batch_id)

    def work_forever(self) -> None:
        while True:
            self.run_one(self.pending_batch_ids.get())

    def run_one(self, batch_id: int) -> None:
        try:
            self.process_batch(batch_id)
        except Exception:
            logger.exception("Batch %s crashed outside the pipeline's own error handling", batch_id)
        finally:
            self.after_each_batch()
            self.pending_batch_ids.task_done()
