from collections.abc import Generator
import logging

from sqlalchemy.exc import OperationalError
from app import database

SessionLocal = database.SessionLocal
logger = logging.getLogger(__name__)


def _is_sqlite_already_exists_error(exc: OperationalError, engine_backend: str) -> bool:
    if engine_backend != "sqlite":
        return False
    message = str(getattr(exc, "orig", exc)).lower()
    return "already exists" in message


def init_db() -> None:
    engine = database.get_engine()
    try:
        database.Base.metadata.create_all(bind=engine)
    except OperationalError as exc:
        if not _is_sqlite_already_exists_error(exc, engine.url.get_backend_name()):
            raise
        logger.warning("sqlite init race detected during create_all; retrying once")
        database.Base.metadata.create_all(bind=engine)


def get_db() -> Generator:
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()
