from collections.abc import Generator

import pytest

from app import database
from app.persistence.session import init_db


@pytest.fixture(autouse=True)
def reset_database(tmp_path) -> Generator[None, None, None]:
    db_path = tmp_path / "fleetwarden-test.db"
    engine = database.configure_database(f"sqlite:///{db_path}")
    init_db()
    yield
    engine.dispose()
    database.configure_database()


@pytest.fixture
def db_session() -> Generator:
    with database.SessionLocal() as session:
        yield session
