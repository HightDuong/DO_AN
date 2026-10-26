"""Kết nối PostgreSQL (Supabase) qua SQLAlchemy.

DATABASE_URL được đọc từ file .env qua app.config.
"""
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


def _normalize_url(url: str) -> str:
    # SQLAlchemy không chấp nhận scheme "postgres://" (Supabase đôi khi cấp dạng này).
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + url[len("postgresql://"):]
    return url


engine = create_engine(
    _normalize_url(settings.database_url),
    pool_pre_ping=True,  # tránh lỗi kết nối bị Supabase đóng khi idle
    pool_size=5,
    max_overflow=5,
    connect_args={"sslmode": "require", "connect_timeout": 10},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: mở một session cho mỗi request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
