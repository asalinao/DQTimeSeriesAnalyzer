import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.db.session import SessionLocal, init_db
from app.models import Monitor, Run
from app.services.runner import execute_monitor


def schedule_interval(monitor: Monitor) -> timedelta:
    try:
        value = int(monitor.schedule_value)
    except ValueError:
        value = 5
    if monitor.schedule_type == "hourly":
        return timedelta(hours=value)
    if monitor.schedule_type == "daily":
        return timedelta(days=value)
    return timedelta(minutes=value)


def as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def latest_run_at(monitor_id: str) -> datetime | None:
    with SessionLocal() as db:
        return db.scalar(select(func.max(Run.created_at)).where(Run.monitor_id == monitor_id))


def is_due(monitor: Monitor, now: datetime | None = None) -> bool:
    if not monitor.is_active:
        return False
    last_run = latest_run_at(monitor.id)
    if last_run is None:
        return True
    return as_utc(last_run) + schedule_interval(monitor) <= (now or datetime.now(timezone.utc))


def due_monitor_ids() -> list[str]:
    with SessionLocal() as db:
        monitors = list(db.scalars(select(Monitor).where(Monitor.is_active.is_(True))))
    return [monitor.id for monitor in monitors if is_due(monitor)]


def main() -> None:
    init_db()
    while True:
        for monitor_id in due_monitor_ids():
            with SessionLocal() as db:
                try:
                    execute_monitor(db, monitor_id)
                except Exception:
                    pass
        time.sleep(60)


if __name__ == "__main__":
    main()
