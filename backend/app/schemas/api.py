from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ConnectionBase(BaseModel):
    name: str
    db_type: str = "postgresql"
    host: str
    port: int = 5432
    database: str
    username: str
    ssl_params: dict[str, Any] = Field(default_factory=dict)


class ConnectionCreate(ConnectionBase):
    password: str


class ConnectionUpdate(BaseModel):
    name: str | None = None
    host: str | None = None
    port: int | None = None
    database: str | None = None
    username: str | None = None
    password: str | None = None
    ssl_params: dict[str, Any] | None = None


class ConnectionRead(ConnectionBase):
    id: str
    last_check_status: str
    last_check_error: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MonitorBase(BaseModel):
    name: str
    connection_id: str
    schema_name: str
    table_name: str
    schedule_type: str = "minutes"
    schedule_value: str = "5"
    timezone: str = "UTC"
    checkpoint_column: str
    checkpoint_type: str = "timestamp"
    selected_metrics: dict[str, list[str]] = Field(default_factory=dict)
    model_config_data: dict[str, Any] = Field(default_factory=dict, alias="model_config")
    static_rules: dict[str, Any] = Field(default_factory=dict)
    notification_config: dict[str, Any] = Field(default_factory=dict)
    query_timeout_seconds: int = 60
    is_active: bool = False


class MonitorCreate(MonitorBase):
    pass


class MonitorUpdate(BaseModel):
    name: str | None = None
    connection_id: str | None = None
    schema_name: str | None = None
    table_name: str | None = None
    schedule_type: str | None = None
    schedule_value: str | None = None
    timezone: str | None = None
    checkpoint_column: str | None = None
    checkpoint_type: str | None = None
    selected_metrics: dict[str, list[str]] | None = None
    model_config_data: dict[str, Any] | None = Field(default=None, alias="model_config")
    static_rules: dict[str, Any] | None = None
    notification_config: dict[str, Any] | None = None
    query_timeout_seconds: int | None = None
    is_active: bool | None = None


class MonitorRead(MonitorBase):
    id: str
    last_successful_checkpoint: str | None = None
    last_successful_run_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class RunRead(BaseModel):
    id: str
    monitor_id: str
    scheduled_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    previous_checkpoint: str | None = None
    current_checkpoint: str | None = None
    new_rows: int
    metrics_count: int
    duration_ms: int | None = None
    error: str | None = None
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SeriesRead(BaseModel):
    id: str
    monitor_id: str
    column_name: str
    metric_name: str
    display_name: str
    model_config_data: dict[str, Any] = Field(default_factory=dict, alias="model_config")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class SeriesPointRead(BaseModel):
    id: str
    series_id: str
    run_id: str
    timestamp: datetime
    actual_value: float | None = None
    predicted_value: float | None = None
    lower_bound: float | None = None
    upper_bound: float | None = None
    is_anomaly: bool
    deviation_score: float | None = None
    model_version: str | None = None

    model_config = ConfigDict(from_attributes=True)


class AnomalyRead(BaseModel):
    id: str
    series_id: str
    run_id: str
    point_id: str
    actual_value: float | None = None
    predicted_value: float | None = None
    lower_bound: float | None = None
    upper_bound: float | None = None
    absolute_deviation: float | None = None
    relative_deviation: float | None = None
    severity: str
    status: str
    reason: str
    created_at: datetime
    closed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class AnomalyStatusUpdate(BaseModel):
    status: str


class DashboardRead(BaseModel):
    active_monitors: int
    runs_24h: int
    failed_runs_24h: int
    open_anomalies: int
    critical_anomalies: int
    connections: dict[str, int]
    latest_runs: list[RunRead]
    latest_anomalies: list[AnomalyRead]
