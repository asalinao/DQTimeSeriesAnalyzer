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
    return DashboardRead(
        active_monitors=count(db, select(func.count(Monitor.id)).where(Monitor.is_active.is_(True))),
        runs_24h=count(db, select(func.count(Run.id)).where(Run.created_at >= since)),
        failed_runs_24h=count(db, select(func.count(Run.id)).where(Run.created_at >= since, Run.status == "failed")),
        open_anomalies=count(db, select(func.count(Anomaly.id)).where(Anomaly.status != "closed")),
        critical_anomalies=count(db, select(func.count(Anomaly.id)).where(Anomaly.status != "closed", Anomaly.severity == "critical")),
        connections={
            "total": count(db, select(func.count(Connection.id))),
            "ok": count(db, select(func.count(Connection.id)).where(Connection.last_check_status == "ok")),
            "failed": count(db, select(func.count(Connection.id)).where(Connection.last_check_status == "failed")),
        },
        latest_runs=list(db.scalars(select(Run).order_by(Run.created_at.desc()).limit(10))),
        latest_anomalies=list(db.scalars(select(Anomaly).order_by(Anomaly.created_at.desc()).limit(10))),
    )


def count(db: Session, stmt) -> int:
    return int(db.scalar(stmt) or 0)
