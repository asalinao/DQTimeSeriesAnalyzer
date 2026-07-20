from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Anomaly, Monitor, Notification, Run, Series
from app.schemas.api import MonitorCreate, MonitorUpdate
from app.services.connections import get_connection
from app.services.sql_safety import ensure_identifier


SCHEDULE_TYPES = {"minutes", "hourly", "daily"}


def _apply_payload(monitor: Monitor, data: dict) -> None:
    model_config = data.pop("model_config_data", None)
    if model_config is not None:
        monitor.model_config = model_config
    for key, value in data.items():
        setattr(monitor, key, value)


def validate_monitor_payload(payload: MonitorCreate | MonitorUpdate) -> None:
    data = payload.model_dump(exclude_unset=True, by_alias=False)
    for key in ("schema_name", "table_name", "checkpoint_column"):
        value = data.get(key)
        if value:
            ensure_identifier(value, key)

    schedule_type = data.get("schedule_type")
    schedule_value = data.get("schedule_value")
    if schedule_type is not None and schedule_type not in SCHEDULE_TYPES:
        raise HTTPException(status_code=422, detail="Неподдерживаемый тип расписания")
    if schedule_value is not None:
        try:
            parsed_value = int(schedule_value)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Значение расписания должно быть целым числом") from exc
        if parsed_value < 1:
            raise HTTPException(status_code=422, detail="Значение расписания должно быть положительным")
        if schedule_type == "minutes" and parsed_value < 5:
            raise HTTPException(status_code=422, detail="Минимальный интервал расписания: 5 минут")


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


def get_monitor(db: Session, monitor_id: str) -> Monitor:
    monitor = db.get(Monitor, monitor_id)
    if not monitor:
        raise HTTPException(status_code=404, detail="Монитор не найден")
    return monitor


def list_monitors(db: Session) -> list[Monitor]:
    return list(db.scalars(select(Monitor).order_by(Monitor.created_at.desc())))


def update_monitor(db: Session, monitor_id: str, payload: MonitorUpdate) -> Monitor:
    monitor = get_monitor(db, monitor_id)
    validate_monitor_payload(payload)
    data = payload.model_dump(exclude_unset=True, by_alias=False)
    if data.get("connection_id"):
        get_connection(db, data["connection_id"])
    _apply_payload(monitor, data)
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
    anomaly_ids = _anomaly_ids_for_monitor(db, series_ids, run_ids)
    if anomaly_ids:
        db.execute(delete(Notification).where(Notification.anomaly_id.in_(anomaly_ids)))
        db.execute(delete(Anomaly).where(Anomaly.id.in_(anomaly_ids)))
    db.delete(monitor)
    db.commit()


def _anomaly_ids_for_monitor(db: Session, series_ids: list[str], run_ids: list[str]) -> list[str]:
    if not series_ids and not run_ids:
        return []
    stmt = select(Anomaly.id)
    if series_ids and run_ids:
        stmt = stmt.where((Anomaly.series_id.in_(series_ids)) | (Anomaly.run_id.in_(run_ids)))
    elif series_ids:
        stmt = stmt.where(Anomaly.series_id.in_(series_ids))
    else:
        stmt = stmt.where(Anomaly.run_id.in_(run_ids))
    return list(db.scalars(stmt))
