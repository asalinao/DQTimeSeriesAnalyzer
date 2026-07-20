from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import require_admin
from app.db.session import get_db
from app.models import Anomaly, Connection, Monitor, Run
from app.models.entities import utcnow
from app.schemas.api import DashboardRead

router = APIRouter(dependencies=[Depends(require_admin)])


@router.get("", response_model=DashboardRead)
def dashboard(db: Session = Depends(get_db)):
    since = utcnow() - timedelta(hours=24)
    active_monitors = db.scalar(select(func.count(Monitor.id)).where(Monitor.is_active.is_(True))) or 0
    runs_24h = db.scalar(select(func.count(Run.id)).where(Run.created_at >= since)) or 0
    failed_runs_24h = db.scalar(select(func.count(Run.id)).where(Run.created_at >= since, Run.status == "failed")) or 0
    open_anomalies = db.scalar(select(func.count(Anomaly.id)).where(Anomaly.status != "closed")) or 0
    critical_anomalies = db.scalar(select(func.count(Anomaly.id)).where(Anomaly.status != "closed", Anomaly.severity == "critical")) or 0
    latest_runs = list(db.scalars(select(Run).order_by(Run.created_at.desc()).limit(10)))
    latest_anomalies = list(db.scalars(select(Anomaly).order_by(Anomaly.created_at.desc()).limit(10)))
    connections = {
        "total": db.scalar(select(func.count(Connection.id))) or 0,
        "ok": db.scalar(select(func.count(Connection.id)).where(Connection.last_check_status == "ok")) or 0,
        "failed": db.scalar(select(func.count(Connection.id)).where(Connection.last_check_status == "failed")) or 0,
    }
    return DashboardRead(
        active_monitors=active_monitors,
        runs_24h=runs_24h,
        failed_runs_24h=failed_runs_24h,
        open_anomalies=open_anomalies,
        critical_anomalies=critical_anomalies,
        connections=connections,
        latest_runs=latest_runs,
        latest_anomalies=latest_anomalies,
    )
