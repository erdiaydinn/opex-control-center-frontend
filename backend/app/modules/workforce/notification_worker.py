"""Durable scheduled push worker. Run as a separate container/process."""

import logging
import os
import time

from . import persistence
from .push import deliver


logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s")
LOGGER = logging.getLogger("workforce.notification_worker")


def run() -> None:
    persistence.initialize()
    interval = max(1, int(os.getenv("WORKFORCE_PUSH_POLL_SECONDS", "5")))
    LOGGER.info("notification worker started")
    while True:
        for job in persistence.claim_due_notifications():
            try:
                deliver(job)
                persistence.finish_notification(job["id"])
            except Exception as error:
                LOGGER.exception("push delivery failed id=%s", job["id"])
                persistence.finish_notification(job["id"], str(error))
        time.sleep(interval)


if __name__ == "__main__":
    run()
