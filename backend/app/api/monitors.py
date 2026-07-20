from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import require_admin
from app.db.session import get_db
from app.schemas.api import MonitorCreate, MonitorRead, MonitorUpdate, RunRead
from app.services.monitors import create_monitor, delete_monitor, get_monitor, list_monitors, set_active, update_monitor
from app.services.runner import execute_monitor


router = APIRouter(dependencies=[Depends(require_admin)])


@router.get("", response_model=list[MonitorRead])
def list_all(db: Session = Depends(get_db)):
    return list_monitors(db)


@router.post("", response_model=MonitorRead)
def create(payload: MonitorCreate, db: Session = Depends(get_db)):
    return create_monitor(db, payload)


@router.get("/{monitor_id}", response_model=MonitorRead)
def get_one(monitor_id: str, db: Session = Depends(get_db)):
    return get_monitor(db, monitor_id)


@router.put("/{monitor_id}", response_model=MonitorRead)
def update(monitor_id: str, payload: MonitorUpdate, db: Session = Depends(get_db)):
    return update_monitor(db, monitor_id, payload)


@router.delete("/{monitor_id}", status_code=204)
def delete(monitor_id: str, db: Session = Depends(get_db)):
    delete_monitor(db, monitor_id)


@router.post("/{monitor_id}/enable", response_model=MonitorRead)
def enable(monitor_id: str, db: Session = Depends(get_db)):
    return set_active(db, monitor_id, True)


@router.post("/{monitor_id}/disable", response_model=MonitorRead)
def disable(monitor_id: str, db: Session = Depends(get_db)):
    return set_active(db, monitor_id, False)


@router.post("/{monitor_id}/run", response_model=RunRead)
def run(monitor_id: str, db: Session = Depends(get_db)):
    return execute_monitor(db, monitor_id)
