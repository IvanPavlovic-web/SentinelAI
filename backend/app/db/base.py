"""SQLAlchemy declarative base, engine, and session dependency."""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


_engine_kwargs: dict = {"pool_pre_ping": True, "future": True}
if not settings.DATABASE_URL.startswith("sqlite"):
    # SQLite's default pool doesn't accept sizing kwargs; Postgres/MySQL do,
    # and this is what lets the API serve many concurrent dashboard/WebSocket
    # clients without exhausting connections under real production load.
    _engine_kwargs.update(
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_timeout=settings.DB_POOL_TIMEOUT_SECONDS,
        pool_recycle=settings.DB_POOL_RECYCLE_SECONDS,
    )

engine = create_engine(settings.DATABASE_URL, **_engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
