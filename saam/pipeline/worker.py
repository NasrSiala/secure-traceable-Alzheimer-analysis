"""Worker mono-consommateur LangGraph : jobs, reprise, heartbeat et santé."""

from __future__ import annotations

import json
import logging
import os
import signal
import socket
import tempfile
import threading
import time
from pathlib import Path
from uuid import uuid4

import psycopg

from saam.cases import InvalidTransition
from saam.pipeline.graph import GraphRunner, WorkerInterrupted

logger = logging.getLogger(__name__)


def database_available(url: str) -> bool:
    if not url:
        return False
    try:
        with psycopg.connect(
            url, connect_timeout=2, options="-c statement_timeout=1500"
        ) as db:
            db.execute("SELECT 1").fetchone()
        return True
    except psycopg.Error:
        return False


def write_status(path: Path, healthy: bool) -> None:
    fd, name = tempfile.mkstemp(prefix=".worker-status-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(
                {"status": "ok" if healthy else "error", "timestamp": time.time()},
                stream,
            )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    stopped = threading.Event()

    def shutdown(_signum: int, _frame: object) -> None:
        stopped.set()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    path = Path(os.environ.get("WORKER_STATUS_FILE", "/run/saam/worker.json"))
    path.parent.mkdir(parents=True, exist_ok=True)
    previous: bool | None = None
    runner: GraphRunner | None = None
    worker_id = socket.gethostname()[:40] + "-" + uuid4().hex
    logger.info("Worker LangGraph factice démarré ; pas d'analyse clinique.")
    try:
        while not stopped.is_set():
            ready = database_available(os.environ.get("DATABASE_URL_WORKER", ""))
            try:
                if ready and runner is None:
                    runner = GraphRunner.from_environment()
                if ready and runner:
                    runner.cases.recover_jobs()
                    job = runner.cases.claim_job(worker_id)
                    write_status(path, True)
                    if job:
                        try:
                            runner.run(
                                job,
                                stop=stopped,
                                report=lambda ok: write_status(path, ok),
                            )
                        except (WorkerInterrupted, InvalidTransition):
                            logger.info("Job interrompu ; reprise par checkpoint.")
                else:
                    ready = False
            except (psycopg.Error, OSError, ValueError):
                ready = False
                if runner:
                    runner.close()
                    runner = None
            write_status(path, ready)
            if ready != previous:
                logger.info(
                    "Pipeline worker : %s", "disponible" if ready else "indisponible"
                )
                previous = ready
            stopped.wait(1)
    finally:
        if runner:
            runner.close()
        write_status(path, False)


if __name__ == "__main__":
    main()
