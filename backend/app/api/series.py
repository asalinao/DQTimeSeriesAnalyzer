from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import require_admin
from app.db.session import get_db
from app.models import Series, SeriesPoint
from app.schemas.api import SeriesPointRead, SeriesRead

router = APIRouter(dependencies=[Depends(require_admin)])


@router.get("/series", response_model=list[SeriesRead])
def list_series(monitor_id: str | None = None, db: Session = Depends(get_db)):
    stmt = select(Series).order_by(Series.created_at.desc())
    if monitor_id:
        stmt = stmt.where(Series.monitor_id == monitor_id)
    return list(db.scalars(stmt))


@router.get("/series/{series_id}/points", response_model=list[SeriesPointRead])
def get_points(
    series_id: str,
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = None,
    limit: int = 5000,
    resolution: str | None = None,
    db: Session = Depends(get_db),
):
    if not db.get(Series, series_id):
        raise HTTPException(status_code=404, detail="Временной ряд не найден")
    max_limit = 2000 if resolution == "overview" else 5000
    stmt = select(SeriesPoint).where(SeriesPoint.series_id == series_id)
    if from_:
        stmt = stmt.where(SeriesPoint.timestamp >= from_)
    if to:
        stmt = stmt.where(SeriesPoint.timestamp <= to)
    return list(db.scalars(stmt.order_by(SeriesPoint.timestamp.desc()).limit(min(max(limit, 1), max_limit))))
