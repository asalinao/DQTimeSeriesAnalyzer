from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import require_admin
from app.db.session import get_db
from app.models import Anomaly
from app.models.entities import utcnow
from app.schemas.api import AnomalyRead, AnomalyStatusUpdate

router = APIRouter(dependencies=[Depends(require_admin)])


@router.get("", response_model=list[AnomalyRead])
def list_all(status: str | None = None, severity: str | None = None, limit: int = 100, db: Session = Depends(get_db)):
    stmt = select(Anomaly)
    if status:
        stmt = stmt.where(Anomaly.status == status)
    if severity:
        stmt = stmt.where(Anomaly.severity == severity)
    return list(db.scalars(stmt.order_by(Anomaly.created_at.desc()).limit(min(limit, 500))))


@router.get("/{anomaly_id}", response_model=AnomalyRead)
def get_one(anomaly_id: str, db: Session = Depends(get_db)):
    anomaly = db.get(Anomaly, anomaly_id)
    if not anomaly:
        raise HTTPException(status_code=404, detail="Аномалия не найдена")
    return anomaly


@router.put("/{anomaly_id}/status", response_model=AnomalyRead)
def update_status(anomaly_id: str, payload: AnomalyStatusUpdate, db: Session = Depends(get_db)):
    anomaly = db.get(Anomaly, anomaly_id)
    if not anomaly:
        raise HTTPException(status_code=404, detail="Аномалия не найдена")
    anomaly.status = payload.status
    if payload.status == "closed":
        anomaly.closed_at = utcnow()
    db.commit()
    db.refresh(anomaly)
    return anomaly
