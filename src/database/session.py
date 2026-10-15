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
        connect_args: dict[str, object] = {}
        pool_options: dict[str, object] = {}
        if DATABASE_URL.startswith("sqlite"):
            connect_args["check_same_thread"] = False
        elif DATABASE_URL.startswith("postgresql+psycopg"):
            # Pooled endpoints (Neon, PgBouncer in transaction mode) can hand
            # each statement to a different server connection, so psycopg's
            # automatic server-side prepared statements must stay off.
            connect_args["prepare_threshold"] = None
            # Serverless instances are many and short-lived: keep each small.
            pool_options = {"pool_size": 2, "max_overflow": 3, "pool_recycle": 300}
        _engine = create_engine(
            DATABASE_URL,
            future=True,
            pool_pre_ping=True,
            connect_args=connect_args,
            **pool_options,
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
            # Audit trail (migration 009).
            ("flag", "VARCHAR(8) DEFAULT ''"),
            ("extracted_snapshot", "TEXT"),
            ("review_status", "VARCHAR(16) DEFAULT ''"),
            ("reviewed_at", "DATETIME"),
        ],
        "lab_observations": [
            ("confidence", "VARCHAR(64) DEFAULT ''"),
            ("extraction_method", "VARCHAR(32) DEFAULT ''"),
            ("range_status", "VARCHAR(64) DEFAULT 'unknown'"),
            ("date_source", "VARCHAR(16) DEFAULT ''"),
        ],
        "processing_jobs": [
            ("retry_attempt", "INTEGER DEFAULT 0"),
            ("retry_max", "INTEGER DEFAULT 0"),
        ],
        "imaging_studies": [
            ("pending_report_document_id", "VARCHAR(36)"),
            ("owner_id", "VARCHAR(36)"),
            ("report_details", "TEXT"),
        ],
        "imaging_report_sections": [
            ("page_end", "INTEGER"),
            ("extraction_method", "VARCHAR(32) DEFAULT ''"),
            ("source_map", "TEXT"),
            ("reviewed_at", "DATETIME"),
        ],
        "documents": [
            ("owner_id", "VARCHAR(36)"),
        ],
        "medication_records": [
            ("owner_id", "VARCHAR(36)"),
            *[(name, "VARCHAR(256) DEFAULT ''") for name in (
                "brand_name", "generic_name", "route", "dose", "frequency", "refills",
                "prescriber", "pharmacy", "prescription_date", "source_session_id", "text_source",
            )],
            ("entry_index", "INTEGER DEFAULT 0"),
            ("source_page", "INTEGER"),
            ("extracted_snapshot", "TEXT"),
            ("review_flags", "TEXT"),
            ("acknowledged_records", "TEXT"),
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
