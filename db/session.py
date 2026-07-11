from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from config import Settings


def _is_sqlite(database_url: str) -> bool:
    return database_url.startswith("sqlite")


def build_engine(settings: Settings) -> Engine:
    is_sqlite = _is_sqlite(settings.database_url)

    engine_kwargs: dict = {"pool_recycle": settings.db_pool_recycle_seconds}
    if is_sqlite:
        engine_kwargs["connect_args"] = {"check_same_thread": False}
    else:
        engine_kwargs["pool_size"] = settings.db_pool_max_size
        engine_kwargs["max_overflow"] = settings.db_pool_max_overflow

    engine = create_engine(settings.database_url, **engine_kwargs)

    if _is_sqlite(settings.database_url):

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragmas(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


class Database:
    def __init__(self, settings: Settings):
        self.engine = build_engine(settings)
        self.session_factory = sessionmaker(
            bind=self.engine, autoflush=False, autocommit=False
        )

    def get_db_session(self) -> Iterator[Session]:
        db = self.session_factory()
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def session_scope(self) -> Iterator[Session]:
        db = self.session_factory()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
