from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import get_settings


Base = declarative_base()
SessionLocal = sessionmaker(autoflush=False, autocommit=False, future=True)
engine = None


def _build_engine(database_url: str):
    connect_args = {"check_same_thread": False, "timeout": 30} if database_url.startswith("sqlite") else {}
    db_engine = create_engine(database_url, connect_args=connect_args, future=True)

    @event.listens_for(db_engine, "connect")
    def configure_sqlite(dbapi_connection, _connection_record):  # type: ignore[no-untyped-def]
        if database_url.startswith("sqlite"):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA busy_timeout=30000;")
            cursor.execute("PRAGMA foreign_keys=ON;")
            cursor.close()

    return db_engine


def configure_database(database_url: str | None = None):
    global engine
    selected_url = database_url or get_settings().database_url
    if engine is not None:
        engine.dispose()
    engine = _build_engine(selected_url)
    SessionLocal.configure(bind=engine)
    return engine


def get_engine():
    if engine is None:
        return configure_database()
    return engine


configure_database()
