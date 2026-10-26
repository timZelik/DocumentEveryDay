"""Pushes to my phone through ntfy. The topic name is the only secret, so the message never holds the token."""

import logging
import urllib.request

logger = logging.getLogger(__name__)


class NtfyNotifier:
    def __init__(self, server_url: str, topic: str, public_base_url: str):
        self.topic_url = f"{server_url.rstrip('/')}/{topic}"
        self.public_base_url = public_base_url.rstrip("/")

    def batch_ready(self, batch_id: int, clip_count: int, total_cost_dollars: float) -> None:
        self.publish(
            title="Your clips are ready",
            message=f"{clip_count} clips to swipe · AI cost ${total_cost_dollars:.4f}",
            click_url=f"{self.public_base_url}/review/{batch_id}",
            tags="clapper",
        )

    def batch_failed(self, batch_id: int, reason: str) -> None:
        self.publish(
            title=f"Batch {batch_id} failed",
            message=reason[:300],
            click_url=f"{self.public_base_url}/review/{batch_id}",
            tags="warning",
        )

    def publish(self, title: str, message: str, click_url: str, tags: str) -> None:
        request = urllib.request.Request(
            self.topic_url,
            data=message.encode(),
            headers={"Title": title, "Click": click_url, "Tags": tags},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=10):
                pass
        except OSError:
            logger.warning("Could not reach ntfy; the review page still has the batch.", exc_info=True)
