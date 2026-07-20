import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def new_uuid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class Connection(Base, TimestampMixin):
    __tablename__ = "connections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    db_type: Mapped[str] = mapped_column(String(32), default="postgresql", nullable=False)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, default=5432, nullable=False)
    database: Mapped[str] = mapped_column(String(255), nullable=False)
    username: Mapped[str] = mapped_column(String(255), nullable=False)
    encrypted_password: Mapped[str] = mapped_column(Text, nullable=False)
    ssl_params: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    last_check_status: Mapped[str] = mapped_column(String(32), default="unchecked", nullable=False)
    last_check_error: Mapped[str | None] = mapped_column(Text)

    monitors: Mapped[list["Monitor"]] = relationship(back_populates="connection", cascade="all, delete-orphan")


class Monitor(Base, TimestampMixin):
    __tablename__ = "monitors"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    connection_id: Mapped[str] = mapped_column(String(36), ForeignKey("connections.id"), nullable=False)
    schema_name: Mapped[str] = mapped_column(String(128), nullable=False)
    table_name: Mapped[str] = mapped_column(String(128), nullable=False)
    schedule_type: Mapped[str] = mapped_column(String(32), default="minutes", nullable=False)
    schedule_value: Mapped[str] = mapped_column(String(128), default="5", nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", nullable=False)
    checkpoint_column: Mapped[str] = mapped_column(String(128), nullable=False)
    checkpoint_type: Mapped[str] = mapped_column(String(32), default="timestamp", nullable=False)
    selected_metrics: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    model_config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    static_rules: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    notification_config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    query_timeout_seconds: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_successful_checkpoint: Mapped[str | None] = mapped_column(String(255))
    last_successful_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    connection: Mapped[Connection] = relationship(back_populates="monitors")
    runs: Mapped[list["Run"]] = relationship(back_populates="monitor", cascade="all, delete-orphan")
    series: Mapped[list["Series"]] = relationship(back_populates="monitor", cascade="all, delete-orphan")


class Run(Base, TimestampMixin):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    monitor_id: Mapped[str] = mapped_column(String(36), ForeignKey("monitors.id"), nullable=False)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    interval_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    interval_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    previous_checkpoint: Mapped[str | None] = mapped_column(String(255))
    current_checkpoint: Mapped[str | None] = mapped_column(String(255))
    new_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    metrics_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="scheduled", nullable=False)

    monitor: Mapped[Monitor] = relationship(back_populates="runs")
    points: Mapped[list["SeriesPoint"]] = relationship(back_populates="run", cascade="all, delete-orphan")


class Series(Base, TimestampMixin):
    __tablename__ = "series"
    __table_args__ = (UniqueConstraint("monitor_id", "column_name", "metric_name", name="uq_series_monitor_column_metric"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    monitor_id: Mapped[str] = mapped_column(String(36), ForeignKey("monitors.id"), nullable=False)
    column_name: Mapped[str] = mapped_column(String(128), nullable=False)
    metric_name: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    model_config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    monitor: Mapped[Monitor] = relationship(back_populates="series")
    points: Mapped[list["SeriesPoint"]] = relationship(back_populates="series", cascade="all, delete-orphan")


class SeriesPoint(Base, TimestampMixin):
    __tablename__ = "series_points"
    __table_args__ = (UniqueConstraint("series_id", "run_id", name="uq_series_point_series_run"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    series_id: Mapped[str] = mapped_column(String(36), ForeignKey("series.id"), nullable=False)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("runs.id"), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    interval_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    interval_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actual_value: Mapped[float | None] = mapped_column(Float)
    predicted_value: Mapped[float | None] = mapped_column(Float)
    lower_bound: Mapped[float | None] = mapped_column(Float)
    upper_bound: Mapped[float | None] = mapped_column(Float)
    is_anomaly: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deviation_score: Mapped[float | None] = mapped_column(Float)
    model_version: Mapped[str | None] = mapped_column(String(64))
    model_details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    series: Mapped[Series] = relationship(back_populates="points")
    run: Mapped[Run] = relationship(back_populates="points")
    anomaly: Mapped["Anomaly | None"] = relationship(back_populates="point", cascade="all, delete-orphan")


class Anomaly(Base, TimestampMixin):
    __tablename__ = "anomalies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    series_id: Mapped[str] = mapped_column(String(36), ForeignKey("series.id"), nullable=False)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("runs.id"), nullable=False)
    point_id: Mapped[str] = mapped_column(String(36), ForeignKey("series_points.id"), nullable=False)
    actual_value: Mapped[float | None] = mapped_column(Float)
    predicted_value: Mapped[float | None] = mapped_column(Float)
    lower_bound: Mapped[float | None] = mapped_column(Float)
    upper_bound: Mapped[float | None] = mapped_column(Float)
    absolute_deviation: Mapped[float | None] = mapped_column(Float)
    relative_deviation: Mapped[float | None] = mapped_column(Float)
    severity: Mapped[str] = mapped_column(String(32), default="warning", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="new", nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    point: Mapped[SeriesPoint] = relationship(back_populates="anomaly")
    run: Mapped[Run] = relationship()
    series: Mapped[Series] = relationship()


class Notification(Base, TimestampMixin):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    anomaly_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("anomalies.id"))
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)
