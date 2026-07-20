import time
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.db.session import SessionLocal, init_db
from app.models import Monitor, Run
from app.services.runner import execute_monitor
from app.services.scheduling import next_scheduled_at


def latest_run_at(monitor_id: str) -> datetime | None:
    with SessionLocal() as db:
        return db.scalar(select(func.max(Run.created_at)).where(Run.monitor_id == monitor_id))


def is_due(monitor: Monitor, now: datetime | None = None) -> bool:
    if not monitor.is_active:
        return False
    current = now or datetime.now(timezone.utc)
    last_run = latest_run_at(monitor.id)
    base = last_run or monitor.created_at
    try:
        return next_scheduled_at(monitor.schedule_cron, monitor.timezone, base) <= current
    except ValueError:
        return False


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
