from datetime import datetime, timezone
from decimal import Decimal
from time import perf_counter
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Anomaly, Monitor, Run, Series, SeriesPoint
from app.models.entities import utcnow
from app.notifications.webhook import create_notification, send_webhook
from app.services import source_postgres
from app.services.monitors import get_monitor
from app.services.sql_safety import MetricSpec, build_aggregate_sql, parse_checkpoint
from app.timeseries.models import Forecast, compare, forecast_next


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
    _mark_running(db, run, monitor)

    try:
        current_checkpoint = source_postgres.fetch_current_checkpoint(
            monitor.connection,
            monitor.schema_name,
            monitor.table_name,
            monitor.checkpoint_column,
        )
        if current_checkpoint is None:
            raise RuntimeError("Не удалось определить текущий checkpoint")

        now = datetime.now(timezone.utc)
        sql, specs = build_aggregate_sql(
            monitor.schema_name,
            monitor.table_name,
            monitor.checkpoint_column,
            monitor.selected_metrics,
            monitor.last_successful_checkpoint,
        )
        metrics = source_postgres.execute_aggregate(
            monitor.connection,
            sql,
            {
                "previous_checkpoint": monitor.last_successful_checkpoint,
                "current_checkpoint": current_checkpoint,
                "last_successful_run_at": monitor.last_successful_run_at,
                "current_run_at": now,
            },
            monitor.query_timeout_seconds,
        )

        point_time = checkpoint_datetime(current_checkpoint, now)
        run.current_checkpoint = current_checkpoint
        run.interval_start = checkpoint_datetime(monitor.last_successful_checkpoint, now) if monitor.last_successful_checkpoint else None
        run.interval_end = point_time
        run.metrics_count = _store_points(db, monitor, run, specs, metrics, point_time)
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
        return _mark_partial_success(db, run.id)
    except Exception as exc:
        db.rollback()
        return _mark_failed(db, run.id, exc, started)


def _store_points(
    db: Session,
    monitor: Monitor,
    run: Run,
    specs: list[MetricSpec],
    metrics: dict[str, Any],
    point_time: datetime,
) -> int:
    created = 0
    for spec in specs:
        series = get_or_create_series(db, monitor, spec)
        if _point_exists(db, series.id, run.id):
            continue
        actual = to_float(metrics.get(spec.alias))
        forecast = forecast_for_series(db, series, monitor)
        rules = rules_for_series(monitor, series, spec)
        is_anomaly, _reason, severity, absolute, relative = compare(actual, forecast, rules)
        point = SeriesPoint(
            series_id=series.id,
            run_id=run.id,
            timestamp=point_time,
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
        created += 1
        if spec.column_name == "__table__" and spec.metric_name == "row_count":
            run.new_rows = int(actual or 0)
        if is_anomaly:
            create_anomaly(db, monitor, series, point, actual, forecast, absolute, relative, severity)
    return created


def create_anomaly(
    db: Session,
    monitor: Monitor,
    series: Series,
    point: SeriesPoint,
    actual: float | None,
    forecast: Forecast,
    absolute: float | None,
    relative: float | None,
    severity: str,
) -> None:
    anomaly = Anomaly(
        series_id=series.id,
        run_id=point.run_id,
        point_id=point.id,
        actual_value=actual,
        predicted_value=forecast.predicted,
        lower_bound=forecast.lower,
        upper_bound=forecast.upper,
        absolute_deviation=absolute,
        relative_deviation=relative,
        severity=severity,
        reason=f"{monitor.schema_name}.{monitor.table_name}, {series.column_name}, {series.metric_name}",
    )
    db.add(anomaly)
    db.flush()
    notify(db, monitor, series, anomaly)


def notify(db: Session, monitor: Monitor, series: Series, anomaly: Anomaly) -> None:
    payload = {
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
    notification = create_notification(db, "dq_anomaly_detected", payload, anomaly.id)
    webhook_url = (monitor.notification_config or {}).get("webhook_url")
    if webhook_url:
        send_webhook(db, notification, webhook_url)
    else:
        notification.status = "ui"


def get_or_create_series(db: Session, monitor: Monitor, spec: MetricSpec) -> Series:
    series = db.scalar(
        select(Series).where(
            Series.monitor_id == monitor.id,
            Series.column_name == spec.column_name,
            Series.metric_name == spec.metric_name,
        )
    )
    if series is not None:
        return series
    display_name = spec.metric_name if spec.column_name == "__table__" else f"{spec.column_name}.{spec.metric_name}"
    series = Series(
        monitor_id=monitor.id,
        column_name=spec.column_name,
        metric_name=spec.metric_name,
        display_name=display_name,
        model_config=monitor.model_config or {},
    )
    db.add(series)
    db.flush()
    return series


def forecast_for_series(db: Session, series: Series, monitor: Monitor) -> Forecast:
    window = max(get_settings().min_series_points, int((monitor.model_config or {}).get("window", 30)))
    points = db.scalars(
        select(SeriesPoint).where(SeriesPoint.series_id == series.id).order_by(SeriesPoint.timestamp.desc()).limit(window * 2)
    ).all()
    history = [point.actual_value for point in reversed(points)]
    return forecast_next(history, series.model_config or monitor.model_config or {}, get_settings().min_series_points)


def rules_for_series(monitor: Monitor, series: Series, spec: MetricSpec) -> dict:
    rules = monitor.static_rules or {}
    return rules.get(series.display_name) or rules.get(spec.metric_name) or {}


def checkpoint_datetime(raw: Any, fallback: datetime) -> datetime:
    checkpoint = parse_checkpoint(raw)
    if checkpoint is None:
        return fallback
    try:
        parsed = datetime.fromisoformat(checkpoint.replace("Z", "+00:00"))
    except ValueError:
        return fallback
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def to_float(value: Any) -> float | None:
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


def _has_running_run(db: Session, monitor_id: str) -> bool:
    return (db.scalar(select(func.count(Run.id)).where(Run.monitor_id == monitor_id, Run.status == "running")) or 0) > 0


def _point_exists(db: Session, series_id: str, run_id: str) -> bool:
    return (db.scalar(select(func.count(SeriesPoint.id)).where(SeriesPoint.series_id == series_id, SeriesPoint.run_id == run_id)) or 0) > 0


def _mark_running(db: Session, run: Run, monitor: Monitor) -> None:
    run.status = "running"
    run.started_at = utcnow()
    run.previous_checkpoint = monitor.last_successful_checkpoint
    db.commit()


def _mark_partial_success(db: Session, run_id: str) -> Run:
    run = db.get(Run, run_id)
    if run is None:
        raise RuntimeError("Запуск не найден после конфликта записи")
    run.status = "partial_success"
    run.error = "Повторный запуск не создал дубликаты точек"
    db.commit()
    db.refresh(run)
    return run


def _mark_failed(db: Session, run_id: str, error: Exception, started: float) -> Run:
    run = db.get(Run, run_id)
    if run is None:
        raise error
    run.status = "failed"
    run.error = str(error)
    run.finished_at = utcnow()
    run.duration_ms = int((perf_counter() - started) * 1000)
    db.commit()
    db.refresh(run)
    return run
