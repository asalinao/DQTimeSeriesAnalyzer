import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.db.session import SessionLocal, init_db
from app.models import Monitor, Run
from app.services.runner import execute_monitor


def _schedule_interval(monitor: Monitor) -> timedelta:
    try:
        value = int(monitor.schedule_value)
    except ValueError:
        return timedelta(minutes=5)
    if monitor.schedule_type == "minutes":
        return timedelta(minutes=value)
    if monitor.schedule_type == "hourly":
        return timedelta(hours=value)
    if monitor.schedule_type == "daily":
        return timedelta(days=value)
    return timedelta(minutes=5)


def _latest_run_at(db, monitor_id: str) -> datetime | None:
    return db.scalar(select(func.max(Run.created_at)).where(Run.monitor_id == monitor_id))


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def is_due(db, monitor: Monitor, now: datetime | None = None) -> bool:
    if not monitor.is_active:
        return False
    current_time = now or datetime.now(timezone.utc)
    last_run_at = _latest_run_at(db, monitor.id)
    if last_run_at is None:
        return True
    return _as_utc(last_run_at) + _schedule_interval(monitor) <= current_time


def due_monitors() -> list[str]:
    with SessionLocal() as db:
        monitors = list(db.scalars(select(Monitor).where(Monitor.is_active.is_(True))))
        return [monitor.id for monitor in monitors if is_due(db, monitor)]


def main() -> None:
    init_db()
    while True:
        for monitor_id in due_monitors():
            with SessionLocal() as db:
                try:
                    execute_monitor(db, monitor_id)
                except Exception:
                    pass
        time.sleep(60)


if __name__ == "__main__":
    main()
