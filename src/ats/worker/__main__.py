import importlib
import logging
import threading

from ats.db.pool import create_pool
from ats.settings import get_settings
from ats.worker.loop import install_signal_handlers, run


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    for module in ("ats.worker.handlers", "ats.worker.ingest"):
        importlib.import_module(module)  # importing registers the handlers
    settings = get_settings()
    stop = threading.Event()
    install_signal_handlers(stop)

    pool = create_pool(settings.database_url, settings.db_pool_max_size)
    pool.open(wait=True, timeout=30)
    try:
        run(
            pool,
            stop,
            poll_interval_s=settings.worker_poll_interval_s,
            visibility_timeout_s=settings.queue_visibility_timeout_s,
        )
    finally:
        pool.close()
    logging.getLogger(__name__).info("worker stopped")


if __name__ == "__main__":
    main()
