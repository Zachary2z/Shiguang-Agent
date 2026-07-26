"""Process entrypoint for the one Shiguang Worker."""

from __future__ import annotations

import asyncio
import secrets
import signal

from app.config import load_settings
from app.infrastructure.db import Database
from app.infrastructure.jobs import PostgresJobQueue
from app.worker.service import JobWorker, deterministic_noop


async def _run() -> None:
    settings = load_settings()
    database = Database(settings.database_url)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signal_number in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signal_number, stop.set)
    worker = JobWorker(
        queue=PostgresJobQueue(database.session_factory),
        worker_id=f"worker_{secrets.token_hex(8)}",
        handlers={"deterministic.noop": deterministic_noop},
        poll_seconds=settings.worker_poll_seconds,
    )
    try:
        await database.connect()
        await worker.run_forever(stop)
    finally:
        await database.close()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
