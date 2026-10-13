from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from src.config import DATABASE_URL
from src.database.base import Base

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine, _SessionLocal
    if _engine is None:
        connect_args = {}
        if DATABASE_URL.startswith("sqlite"):
            connect_args["check_same_thread"] = False
        _engine = create_engine(
            DATABASE_URL,
            future=True,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
        _SessionLocal = sessionmaker(
            bind=_engine,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
            future=True,
        )
    return _engine


def get_session() -> Session:
    get_engine()
    assert _SessionLocal is not None
    return _SessionLocal()


@contextmanager
def session_scope() -> Iterator[Session]:
    session = get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _ensure_sqlite_columns(engine: Engine) -> None:
    """Add newly introduced columns on existing local SQLite databases."""
    alterations = {
        "extracted_fields": [
            ("extraction_method", "VARCHAR(32) DEFAULT ''"),
        ],
        "lab_observations": [
            ("confidence", "VARCHAR(64) DEFAULT ''"),
            ("extraction_method", "VARCHAR(32) DEFAULT ''"),
            ("range_status", "VARCHAR(64) DEFAULT 'unknown'"),
        ],
        "processing_jobs": [
            ("retry_attempt", "INTEGER DEFAULT 0"),
            ("retry_max", "INTEGER DEFAULT 0"),
        ],
        "imaging_studies": [
            ("pending_report_document_id", "VARCHAR(36)"),
            ("owner_id", "VARCHAR(36)"),
        ],
        "documents": [
            ("owner_id", "VARCHAR(36)"),
        ],
        "medication_records": [
            ("owner_id", "VARCHAR(36)"),
        ],
    }
    with engine.begin() as connection:
        for table, columns in alterations.items():
            existing = {
                row[1]
                for row in connection.execute(text(f"PRAGMA table_info({table})")).fetchall()
            }
            if not existing:
                continue
            for name, definition in columns:
                if name not in existing:
                    connection.execute(
                        text(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
                    )


def init_db() -> None:
    """Create tables when migrations have not been applied yet (local/dev)."""
    # Import models so metadata is populated.
    from src.database import models  # noqa: F401

    engine = get_engine()
    if DATABASE_URL.startswith("sqlite"):
        Base.metadata.create_all(bind=engine)
        _ensure_sqlite_columns(engine)


def probe_database() -> tuple[bool, str]:
    try:
        engine = get_engine()
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        dialect = engine.dialect.name
        return True, f"{dialect} connected"
    except Exception as error:
        return False, f"{type(error).__name__}: {error}"
