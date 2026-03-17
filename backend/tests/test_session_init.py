import sqlite3

import pytest
from sqlalchemy.exc import OperationalError

from app import database
from app.persistence.session import init_db


def _sqlite_operational_error(message: str) -> OperationalError:
    return OperationalError("CREATE TABLE nodes (...)", {}, sqlite3.OperationalError(message))


def test_init_db_retries_once_on_sqlite_already_exists(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    def flaky_create_all(*args, **kwargs) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise _sqlite_operational_error("table nodes already exists")

    monkeypatch.setattr(database.Base.metadata, "create_all", flaky_create_all)

    init_db()

    assert calls == 2


def test_init_db_does_not_swallow_unrelated_operational_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken_create_all(*args, **kwargs) -> None:
        raise _sqlite_operational_error("database is locked")

    monkeypatch.setattr(database.Base.metadata, "create_all", broken_create_all)

    with pytest.raises(OperationalError):
        init_db()

