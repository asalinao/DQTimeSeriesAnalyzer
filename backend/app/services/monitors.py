from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Anomaly, Monitor, Notification, Run, Series
from app.schemas.api import MonitorCreate, MonitorUpdate
from app.services.connections import get_connection
from app.services.sql_safety import UnsafeSqlError, ensure_identifier


SCHEDULE_TYPES = {"minutes", "hourly", "daily"}


def list_monitors(db: Session) -> list[Monitor]:
    return list(db.scalars(select(Monitor).order_by(Monitor.created_at.desc())))


def get_monitor(db: Session, monitor_id: str) -> Monitor:
    monitor = db.get(Monitor, monitor_id)
    if monitor is None:
        raise HTTPException(status_code=404, detail="Монитор не найден")
    return monitor


def create_monitor(db: Session, payload: MonitorCreate) -> Monitor:
    get_connection(db, payload.connection_id)
    validate_monitor_payload(payload)
    data = payload.model_dump(by_alias=False)
    model_config = data.pop("model_config_data")
    monitor = Monitor(**data)
    monitor.model_config = model_config
    db.add(monitor)
    db.commit()
    db.refresh(monitor)
    return monitor


def update_monitor(db: Session, monitor_id: str, payload: MonitorUpdate) -> Monitor:
    monitor = get_monitor(db, monitor_id)
    validate_monitor_payload(payload)
    data = payload.model_dump(exclude_unset=True, by_alias=False)
    if data.get("connection_id"):
        get_connection(db, data["connection_id"])
    model_config = data.pop("model_config_data", None)
    if model_config is not None:
        monitor.model_config = model_config
    for field, value in data.items():
        setattr(monitor, field, value)
    db.commit()
    db.refresh(monitor)
    return monitor


def set_active(db: Session, monitor_id: str, active: bool) -> Monitor:
    monitor = get_monitor(db, monitor_id)
    monitor.is_active = active
    db.commit()
    db.refresh(monitor)
    return monitor


def delete_monitor(db: Session, monitor_id: str) -> None:
    monitor = get_monitor(db, monitor_id)
    series_ids = list(db.scalars(select(Series.id).where(Series.monitor_id == monitor_id)))
    run_ids = list(db.scalars(select(Run.id).where(Run.monitor_id == monitor_id)))
    anomaly_ids: list[str] = []
    if series_ids:
        anomaly_ids.extend(db.scalars(select(Anomaly.id).where(Anomaly.series_id.in_(series_ids))))
    if run_ids:
        anomaly_ids.extend(db.scalars(select(Anomaly.id).where(Anomaly.run_id.in_(run_ids))))
    anomaly_ids = list(set(anomaly_ids))
    if anomaly_ids:
        db.execute(delete(Notification).where(Notification.anomaly_id.in_(anomaly_ids)))
        db.execute(delete(Anomaly).where(Anomaly.id.in_(anomaly_ids)))
    db.delete(monitor)
    db.commit()


def validate_monitor_payload(payload: MonitorCreate | MonitorUpdate) -> None:
    data = payload.model_dump(exclude_unset=True, by_alias=False)
    try:
        for field in ("schema_name", "table_name", "checkpoint_column"):
            if value := data.get(field):
                ensure_identifier(value, field)
    except UnsafeSqlError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    schedule_type = data.get("schedule_type")
    schedule_value = data.get("schedule_value")
    if schedule_type is not None and schedule_type not in SCHEDULE_TYPES:
        raise HTTPException(status_code=422, detail="Неподдерживаемый тип расписания")
    if schedule_value is None:
        return
    try:
        parsed = int(schedule_value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Значение расписания должно быть целым числом") from exc
    if parsed < 1:
        raise HTTPException(status_code=422, detail="Значение расписания должно быть положительным")
    if schedule_type == "minutes" and parsed < 5:
        raise HTTPException(status_code=422, detail="Минимальный интервал расписания: 5 минут")
