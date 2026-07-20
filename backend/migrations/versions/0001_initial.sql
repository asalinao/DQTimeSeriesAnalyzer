CREATE TABLE connections (
    id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    db_type VARCHAR(32) NOT NULL DEFAULT 'postgresql',
    host VARCHAR(255) NOT NULL,
    port INTEGER NOT NULL DEFAULT 5432,
    database VARCHAR(255) NOT NULL,
    username VARCHAR(255) NOT NULL,
    encrypted_password TEXT NOT NULL,
    ssl_params JSON NOT NULL,
    last_check_status VARCHAR(32) NOT NULL DEFAULT 'unchecked',
    last_check_error TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE monitors (
    id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    connection_id VARCHAR(36) NOT NULL REFERENCES connections(id),
    schema_name VARCHAR(128) NOT NULL,
    table_name VARCHAR(128) NOT NULL,
    schedule_type VARCHAR(32) NOT NULL DEFAULT 'minutes',
    schedule_value VARCHAR(128) NOT NULL DEFAULT '5',
    timezone VARCHAR(64) NOT NULL DEFAULT 'UTC',
    checkpoint_column VARCHAR(128) NOT NULL,
    checkpoint_type VARCHAR(32) NOT NULL DEFAULT 'timestamp',
    selected_metrics JSON NOT NULL,
    model_config JSON NOT NULL,
    static_rules JSON NOT NULL,
    notification_config JSON NOT NULL,
    query_timeout_seconds INTEGER NOT NULL DEFAULT 60,
    is_active BOOLEAN NOT NULL DEFAULT FALSE,
    last_successful_checkpoint VARCHAR(255),
    last_successful_run_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE runs (
    id VARCHAR(36) PRIMARY KEY,
    monitor_id VARCHAR(36) NOT NULL REFERENCES monitors(id),
    scheduled_at TIMESTAMPTZ,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    interval_start TIMESTAMPTZ,
    interval_end TIMESTAMPTZ,
    previous_checkpoint VARCHAR(255),
    current_checkpoint VARCHAR(255),
    new_rows INTEGER NOT NULL DEFAULT 0,
    metrics_count INTEGER NOT NULL DEFAULT 0,
    duration_ms INTEGER,
    error TEXT,
    status VARCHAR(32) NOT NULL DEFAULT 'scheduled',
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE series (
    id VARCHAR(36) PRIMARY KEY,
    monitor_id VARCHAR(36) NOT NULL REFERENCES monitors(id),
    column_name VARCHAR(128) NOT NULL,
    metric_name VARCHAR(128) NOT NULL,
    display_name VARCHAR(255) NOT NULL,
    model_config JSON NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT uq_series_monitor_column_metric UNIQUE (monitor_id, column_name, metric_name)
);

CREATE TABLE series_points (
    id VARCHAR(36) PRIMARY KEY,
    series_id VARCHAR(36) NOT NULL REFERENCES series(id),
    run_id VARCHAR(36) NOT NULL REFERENCES runs(id),
    timestamp TIMESTAMPTZ NOT NULL,
    interval_start TIMESTAMPTZ,
    interval_end TIMESTAMPTZ,
    actual_value DOUBLE PRECISION,
    predicted_value DOUBLE PRECISION,
    lower_bound DOUBLE PRECISION,
    upper_bound DOUBLE PRECISION,
    is_anomaly BOOLEAN NOT NULL DEFAULT FALSE,
    deviation_score DOUBLE PRECISION,
    model_version VARCHAR(64),
    model_details JSON NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT uq_series_point_series_run UNIQUE (series_id, run_id)
);

CREATE TABLE anomalies (
    id VARCHAR(36) PRIMARY KEY,
    series_id VARCHAR(36) NOT NULL REFERENCES series(id),
    run_id VARCHAR(36) NOT NULL REFERENCES runs(id),
    point_id VARCHAR(36) NOT NULL REFERENCES series_points(id),
    actual_value DOUBLE PRECISION,
    predicted_value DOUBLE PRECISION,
    lower_bound DOUBLE PRECISION,
    upper_bound DOUBLE PRECISION,
    absolute_deviation DOUBLE PRECISION,
    relative_deviation DOUBLE PRECISION,
    severity VARCHAR(32) NOT NULL DEFAULT 'warning',
    status VARCHAR(32) NOT NULL DEFAULT 'new',
    reason VARCHAR(255) NOT NULL DEFAULT 'forecast_bounds',
    closed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE notifications (
    id VARCHAR(36) PRIMARY KEY,
    event_type VARCHAR(128) NOT NULL,
    anomaly_id VARCHAR(36) REFERENCES anomalies(id),
    payload JSON NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);
