from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


def engine_kwargs(url: str) -> dict:
    if url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    return {"pool_pre_ping": True}


engine = create_engine(get_settings().database_url, future=True, **engine_kwargs(get_settings().database_url))
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, future=True)


def init_db() -> None:
    from app.models import entities  # noqa: F401

    Base.metadata.create_all(bind=engine)
    ensure_lightweight_migrations()


def ensure_lightweight_migrations() -> None:
    inspector = inspect(engine)
    if "monitors" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("monitors")}
    if "schedule_cron" in columns:
        return
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE monitors ADD COLUMN schedule_cron VARCHAR(128) NOT NULL DEFAULT '*/5 * * * *'"))
        if {"schedule_type", "schedule_value"}.issubset(columns):
            connection.execute(
                text(
                    """
                    UPDATE monitors
                    SET schedule_cron = CASE
                        WHEN schedule_type = 'hourly' THEN '0 */' || schedule_value || ' * * *'
                        WHEN schedule_type = 'daily' THEN '0 0 */' || schedule_value || ' * *'
                        ELSE '*/' || schedule_value || ' * * * *'
                    END
                    """
                )
            )


def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as db:
        yield db
