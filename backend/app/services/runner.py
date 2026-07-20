from datetime import datetime, timezone
from decimal import Decimal
from time import perf_counter
from typing import Any

from fastapi import HTTPException
from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Anomaly, Monitor, Run, Series, SeriesPoint
from app.models.entities import utcnow
from app.notifications.webhook import create_notification, send_webhook
from app.services import source_postgres
from app.services.monitors import get_monitor
from app.services.sql_safety import build_aggregate_sql, parse_checkpoint
from app.timeseries.models import compare, forecast_next


def _float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _checkpoint_timestamp(raw: Any, fallback: datetime) -> datetime:
    checkpoint = parse_checkpoint(raw)
    if not checkpoint:
        return fallback
    try:
        parsed = datetime.fromisoformat(checkpoint.replace("Z", "+00:00"))
    except ValueError:
        return fallback
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _get_or_create_series(db: Session, monitor: Monitor, column_name: str, metric_name: str) -> Series:
    stmt: Select = select(Series).where(
        Series.monitor_id == monitor.id,
        Series.column_name == column_name,
        Series.metric_name == metric_name,
    )
    series = db.scalar(stmt)
    if series:
        return series

    display = metric_name if column_name == "__table__" else f"{column_name}.{metric_name}"
    series = Series(
        monitor_id=monitor.id,
        column_name=column_name,
        metric_name=metric_name,
        display_name=display,
        model_config=monitor.model_config or {},
    )
    db.add(series)
    db.flush()
    return series


def _previous_values(db: Session, series_id: str, limit: int) -> list[float | None]:
    rows = db.scalars(
        select(SeriesPoint).where(SeriesPoint.series_id == series_id).order_by(SeriesPoint.timestamp.desc()).limit(limit)
    ).all()
    return [row.actual_value for row in reversed(rows)]


def _point_exists(db: Session, series_id: str, run_id: str) -> bool:
    return db.scalar(select(func.count(SeriesPoint.id)).where(SeriesPoint.series_id == series_id, SeriesPoint.run_id == run_id)) > 0


def _payload_for_anomaly(monitor: Monitor, series: Series, anomaly: Anomaly) -> dict:
    return {
        "event_type": "dq_anomaly_detected",
        "monitor_id": monitor.id,
        "monitor_name": monitor.name,
        "table": f"{monitor.schema_name}.{monitor.table_name}",
        "column": series.column_name,
        "metric": series.metric_name,
        "observed_at": anomaly.created_at.isoformat(),
        "actual": anomaly.actual_value,
        "predicted": anomaly.predicted_value,
        "lower_bound": anomaly.lower_bound,
        "upper_bound": anomaly.upper_bound,
        "severity": anomaly.severity,
        "anomaly_id": anomaly.id,
    }


def _anomaly_reason(monitor: Monitor, series: Series) -> str:
    return f"{monitor.schema_name}.{monitor.table_name}, {series.column_name}, {series.metric_name}"


def _notify(db: Session, monitor: Monitor, series: Series, anomaly: Anomaly) -> None:
    notification = create_notification(db, "dq_anomaly_detected", _payload_for_anomaly(monitor, series, anomaly), anomaly.id)
    webhook_url = (monitor.notification_config or {}).get("webhook_url")
    if webhook_url:
        send_webhook(db, notification, webhook_url)
    else:
        notification.status = "ui"


def _has_running_run(db: Session, monitor_id: str) -> bool:
    return db.scalar(select(func.count(Run.id)).where(Run.monitor_id == monitor_id, Run.status == "running")) > 0


def execute_monitor(db: Session, monitor_id: str, existing_run_id: str | None = None) -> Run:
    monitor = get_monitor(db, monitor_id)
    if _has_running_run(db, monitor.id):
        raise HTTPException(status_code=409, detail="Для монитора уже выполняется запуск")

    run = db.get(Run, existing_run_id) if existing_run_id else None
    if run is None:
        run = Run(monitor_id=monitor.id, scheduled_at=utcnow())
        db.add(run)
        db.flush()

    started = perf_counter()
    run.status = "running"
    run.started_at = utcnow()
    run.previous_checkpoint = monitor.last_successful_checkpoint
    db.commit()

    try:
        current_checkpoint = source_postgres.fetch_current_checkpoint(
            monitor.connection,
            monitor.schema_name,
            monitor.table_name,
            monitor.checkpoint_column,
        )
        if current_checkpoint is None:
            raise RuntimeError("Не удалось определить текущий checkpoint")
        run.current_checkpoint = current_checkpoint

        sql, specs = build_aggregate_sql(
            monitor.schema_name,
            monitor.table_name,
            monitor.checkpoint_column,
            monitor.selected_metrics,
            monitor.last_successful_checkpoint,
        )
        now = datetime.now(timezone.utc)
        point_timestamp = _checkpoint_timestamp(current_checkpoint, now)
        run.interval_start = _checkpoint_timestamp(monitor.last_successful_checkpoint, now) if monitor.last_successful_checkpoint else None
        run.interval_end = point_timestamp
        params = {
            "previous_checkpoint": monitor.last_successful_checkpoint,
            "current_checkpoint": current_checkpoint,
            "last_successful_run_at": monitor.last_successful_run_at,
            "current_run_at": now,
        }
        raw_metrics = source_postgres.execute_aggregate(monitor.connection, sql, params, monitor.query_timeout_seconds)
        created_points = 0

        for spec in specs:
            series = _get_or_create_series(db, monitor, spec.column_name, spec.metric_name)
            if _point_exists(db, series.id, run.id):
                continue

            actual = _float(raw_metrics.get(spec.alias))
            window = max(get_settings().min_series_points, int((monitor.model_config or {}).get("window", 30)))
            history = _previous_values(db, series.id, window * 2)
            forecast = forecast_next(history, series.model_config or monitor.model_config or {}, get_settings().min_series_points)
            rules = (monitor.static_rules or {}).get(series.display_name) or (monitor.static_rules or {}).get(spec.metric_name) or {}
            is_anomaly, _reason, severity, absolute, relative = compare(actual, forecast, rules)
            point = SeriesPoint(
                series_id=series.id,
                run_id=run.id,
                timestamp=point_timestamp,
                interval_start=run.interval_start,
                interval_end=run.interval_end,
                actual_value=actual,
                predicted_value=forecast.predicted,
                lower_bound=forecast.lower,
                upper_bound=forecast.upper,
                is_anomaly=is_anomaly,
                deviation_score=relative,
                model_version=forecast.model_version,
                model_details=forecast.details,
            )
            db.add(point)
            db.flush()
            created_points += 1

            if is_anomaly:
                anomaly = Anomaly(
                    series_id=series.id,
                    run_id=run.id,
                    point_id=point.id,
                    actual_value=actual,
                    predicted_value=forecast.predicted,
                    lower_bound=forecast.lower,
                    upper_bound=forecast.upper,
                    absolute_deviation=absolute,
                    relative_deviation=relative,
                    severity=severity,
                    reason=_anomaly_reason(monitor, series),
                )
                db.add(anomaly)
                db.flush()
                _notify(db, monitor, series, anomaly)

            if spec.column_name == "__table__" and spec.metric_name == "row_count":
                run.new_rows = int(actual or 0)

        run.metrics_count = created_points
        run.status = "success"
        run.finished_at = utcnow()
        run.duration_ms = int((perf_counter() - started) * 1000)
        monitor.last_successful_checkpoint = parse_checkpoint(current_checkpoint)
        monitor.last_successful_run_at = run.finished_at
        db.commit()
        db.refresh(run)
        return run
    except IntegrityError:
        db.rollback()
        run = db.get(Run, run.id)
        if run:
            run.status = "partial_success"
            run.error = "Повторный запуск не создал дубликаты точек"
            db.commit()
            db.refresh(run)
            return run
        raise
    except Exception as exc:
        db.rollback()
        run = db.get(Run, run.id)
        if run:
            run.status = "failed"
            run.error = str(exc)
            run.finished_at = utcnow()
            run.duration_ms = int((perf_counter() - started) * 1000)
            db.commit()
            db.refresh(run)
            return run
        raise
