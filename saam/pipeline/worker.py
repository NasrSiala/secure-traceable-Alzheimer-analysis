"""Processus worker T1.5 ; la prise de jobs et le graphe viendront dans T3.5."""

from __future__ import annotations

import json
import logging
import os
import signal
import threading
import time
from pathlib import Path

import psycopg

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
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps({"status": "ok" if healthy else "error", "timestamp": time.time()}),
        encoding="utf-8",
    )
    temporary.replace(path)


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
    logger.info("Worker prêt ; traitement des jobs prévu dans T3.5.")
    while not stopped.is_set():
        ready = database_available(os.environ.get("DATABASE_URL_WORKER", ""))
        write_status(path, ready)
        if ready != previous:
            logger.info(
                "Connexion PostgreSQL du worker : %s",
                "disponible" if ready else "indisponible",
            )
            previous = ready
        stopped.wait(2)
    write_status(path, False)


if __name__ == "__main__":
    main()
