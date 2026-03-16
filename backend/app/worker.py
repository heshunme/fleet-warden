import logging
import time

from app.config import get_settings
from app.infra.logging import configure_logging
from app.orchestrator.service import OrchestratorService
from app.persistence.session import SessionLocal, init_db


logger = logging.getLogger(__name__)


def main() -> None:
    configure_logging()
    init_db()
    settings = get_settings()
    while True:
        with SessionLocal() as db:
            service = OrchestratorService(db)
            recovered = service.recover_executing_nodes()
            processed = service.process_waiting_nodes()
            if recovered or processed:
                logger.info("worker cycle complete recovered=%s processed=%s", recovered, processed)
        time.sleep(settings.worker_poll_interval_seconds)


if __name__ == "__main__":
    main()
