from __future__ import annotations

import argparse
import os
import random
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import psycopg

from synthetic_orders import ANOMALY_MODES, generate_rows, history_start


API_BASE_URL = os.getenv("API_BASE_URL", "http://backend:8000/api/v1")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "change-me")
SOURCE_DATABASE_URL = os.getenv("SOURCE_DATABASE_URL", "postgresql://source_owner:source_owner@source-postgres:5432/source")


def headers() -> dict[str, str]:
    return {"X-Admin-Token": ADMIN_TOKEN, "Content-Type": "application/json"}


def wait_for_backend(client: httpx.Client, timeout_seconds: int = 60) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            if client.get(f"{API_BASE_URL}/ready", headers=headers()).status_code == 200:
                return
        except httpx.HTTPError:
            time.sleep(1)
            continue
        time.sleep(1)
    raise RuntimeError("Backend is not ready")


def request_json(client: httpx.Client, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any] | list:
    response = client.request(method, f"{API_BASE_URL}{path}", headers=headers(), json=payload)
    response.raise_for_status()
    return response.json()


def ensure_connection(client: httpx.Client) -> str:
    for connection in request_json(client, "GET", "/connections"):
        if connection["name"] == "Demo source PostgreSQL":
            return connection["id"]
    connection = request_json(
        client,
        "POST",
        "/connections",
        {
            "name": "Demo source PostgreSQL",
            "db_type": "postgresql",
            "host": "source-postgres",
            "port": 5432,
            "database": "source",
            "username": "dq_readonly",
            "password": "dq_readonly",
            "ssl_params": {"sslmode": "prefer"},
        },
    )
    request_json(client, "POST", f"/connections/{connection['id']}/test", {})
    return connection["id"]


def create_monitor(client: httpx.Client, connection_id: str) -> str:
    suffix = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    monitor = request_json(
        client,
        "POST",
        "/monitors",
        {
            "name": f"Auto synthetic orders {suffix}",
            "connection_id": connection_id,
            "schema_name": "public",
            "table_name": "demo_orders",
            "schedule_cron": "*/5 * * * *",
            "timezone": "UTC",
            "checkpoint_column": "created_at",
            "checkpoint_type": "timestamp",
            "selected_metrics": {
                "__table__": ["row_count", "empty_batch"],
                "amount": ["avg", "max", "null_ratio", "stddev"],
                "customer_id": ["distinct_count", "unique_ratio"],
                "status": ["distinct_count"],
            },
            "model_config": {"model": "rolling", "window": 30, "k": 3, "min_std": 0.000001},
            "static_rules": {"row_count": {"min_value": 1}, "amount.null_ratio": {"max_value": 0.25}},
            "notification_config": {},
            "query_timeout_seconds": 60,
            "is_active": False,
        },
    )
    return monitor["id"]


def ensure_source_schema(cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS demo_orders (
            id BIGSERIAL PRIMARY KEY,
            created_at TIMESTAMPTZ NOT NULL,
            amount NUMERIC,
            status TEXT,
            customer_id BIGINT
        )
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_demo_orders_created_at ON demo_orders(created_at)")


def insert_rows(cursor, rows) -> int:
    if not rows:
        return 0
    cursor.executemany(
        "INSERT INTO demo_orders(created_at, amount, status, customer_id) VALUES (%s, %s, %s, %s)",
        [(row.created_at, row.amount, row.status, row.customer_id) for row in rows],
    )
    return len(rows)


def next_start(cursor) -> datetime:
    cursor.execute("SELECT MAX(created_at) FROM demo_orders")
    value = cursor.fetchone()[0]
    if value is None:
        return datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    return value.astimezone(UTC).replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)


def reset_source(days: int, base_rate: float) -> int:
    with psycopg.connect(SOURCE_DATABASE_URL, autocommit=True) as conn, conn.cursor() as cursor:
        ensure_source_schema(cursor)
        cursor.execute("TRUNCATE TABLE demo_orders RESTART IDENTITY")
        return insert_rows(cursor, generate_rows(history_start(days), days * 24, base_rate, "normal", late_arrivals_ratio=0.015))


def append_batch(mode: str, hours: int, base_rate: float) -> int:
    with psycopg.connect(SOURCE_DATABASE_URL, autocommit=True) as conn, conn.cursor() as cursor:
        ensure_source_schema(cursor)
        return insert_rows(cursor, generate_rows(next_start(cursor), hours, base_rate, mode))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate >30 source batches and run DQ monitor after each batch")
    parser.add_argument("--normal-runs", type=int, default=31)
    parser.add_argument("--anomaly-runs", type=int, default=1)
    parser.add_argument("--anomaly-mode", choices=ANOMALY_MODES, default="amount_shift")
    parser.add_argument("--hours-per-run", type=int, default=1)
    parser.add_argument("--base-rate", type=float, default=42.0)
    parser.add_argument("--reset-source", action="store_true")
    parser.add_argument("--history-days", type=int, default=45)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.normal_runs < 31:
        raise ValueError("--normal-runs must be at least 31 to pass the 30-point forecast threshold")
    random.seed(args.seed)
    if args.reset_source:
        print(f"source reset: inserted_history_rows={reset_source(args.history_days, args.base_rate)}")

    with httpx.Client(timeout=120.0) as client:
        wait_for_backend(client)
        connection_id = ensure_connection(client)
        monitor_id = create_monitor(client, connection_id)
        print(f"connection_id={connection_id}")
        print(f"monitor_id={monitor_id}")

        baseline = request_json(client, "POST", f"/monitors/{monitor_id}/run", {})
        print(f"baseline run: status={baseline['status']}, new_rows={baseline['new_rows']}")

        for index in range(1, args.normal_runs + 1):
            inserted = append_batch("normal", args.hours_per_run, args.base_rate)
            run = request_json(client, "POST", f"/monitors/{monitor_id}/run", {})
            print(f"normal {index:02d}: inserted={inserted}, status={run['status']}, new_rows={run['new_rows']}")

        for index in range(1, args.anomaly_runs + 1):
            inserted = append_batch(args.anomaly_mode, args.hours_per_run, args.base_rate)
            run = request_json(client, "POST", f"/monitors/{monitor_id}/run", {})
            print(f"anomaly {index:02d}: mode={args.anomaly_mode}, inserted={inserted}, status={run['status']}, new_rows={run['new_rows']}")

        anomalies = request_json(client, "GET", "/anomalies")
        series = request_json(client, "GET", f"/series?monitor_id={monitor_id}")
        open_anomalies = [item for item in anomalies if item.get("status") != "closed"]
        print(f"summary: series={len(series)}, open_anomalies_total={len(open_anomalies)}")


if __name__ == "__main__":
    main()
