import importlib
import logging
import threading

from ats.buildinfo import code_version
from ats.db.pool import create_pool
from ats.settings import get_settings
from ats.worker.loop import install_signal_handlers, run
from ats.worker.registry import HANDLERS
from ats.worker.startup import read_schema_version, startup_summary


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    for module in (
        "ats.worker.handlers",
        "ats.worker.ingest",
        "ats.worker.judge",
        "ats.worker.position_setup",
    ):
        importlib.import_module(module)  # importing registers the handlers
    settings = get_settings()
    stop = threading.Event()
    install_signal_handlers(stop)

    pool = create_pool(settings.database_url, settings.db_pool_max_size)
    pool.open(wait=True, timeout=30)
    logging.getLogger(__name__).info(
        startup_summary(
            version=code_version(),
            schema_version=read_schema_version(pool),
            handlers=HANDLERS,
            llm_model=settings.llm_model,
            llm_rpm=settings.llm_rpm,
            llm_key_set=bool(settings.llm_api_key and settings.llm_api_key.get_secret_value()),
        )
    )
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
