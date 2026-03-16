from collections.abc import Generator

from app import database

SessionLocal = database.SessionLocal


def init_db() -> None:
    database.Base.metadata.create_all(bind=database.get_engine())


def get_db() -> Generator:
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()
