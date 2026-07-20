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


def api_headers() -> dict[str, str]:
    return {"X-Admin-Token": ADMIN_TOKEN, "Content-Type": "application/json"}


def wait_for_backend(client: httpx.Client, timeout_seconds: int = 60) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            response = client.get(f"{API_BASE_URL}/ready", headers=api_headers())
            if response.status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(1)
    raise RuntimeError("Backend is not ready")


def request_json(client: httpx.Client, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any] | list:
    response = client.request(method, f"{API_BASE_URL}{path}", headers=api_headers(), json=payload)
    response.raise_for_status()
    return response.json()


def ensure_connection(client: httpx.Client) -> str:
    connections = request_json(client, "GET", "/connections")
    for connection in connections:
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


def create_monitor(client: httpx.Client, connection_id: str, suffix: str) -> str:
    monitor = request_json(
        client,
        "POST",
        "/monitors",
        {
            "name": f"Auto synthetic orders {suffix}",
            "connection_id": connection_id,
            "schema_name": "public",
            "table_name": "demo_orders",
            "schedule_type": "minutes",
            "schedule_value": "5",
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


def ensure_schema(cur) -> None:
    cur.execute(
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
    cur.execute("CREATE INDEX IF NOT EXISTS ix_demo_orders_created_at ON demo_orders(created_at)")


def get_next_start(cur) -> datetime:
    cur.execute("SELECT MAX(created_at) FROM demo_orders")
    value = cur.fetchone()[0]
    if value is None:
        return datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    return value.astimezone(UTC).replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)


def reset_source(cur, days: int, base_rate: float) -> int:
    cur.execute("TRUNCATE TABLE demo_orders RESTART IDENTITY")
    return insert_rows(cur, generate_rows(history_start(days), days * 24, base_rate, "normal", late_arrivals_ratio=0.015))


def insert_rows(cur, rows) -> int:
    if not rows:
        return 0
    cur.executemany(
        "INSERT INTO demo_orders(created_at, amount, status, customer_id) VALUES (%s, %s, %s, %s)",
        [(row.created_at, row.amount, row.status, row.customer_id) for row in rows],
    )
    return len(rows)


def append_batch(mode: str, hours: int, base_rate: float) -> int:
    with psycopg.connect(SOURCE_DATABASE_URL, autocommit=True) as conn:
        with conn.cursor() as cur:
            ensure_schema(cur)
            return insert_rows(cur, generate_rows(get_next_start(cur), hours, base_rate, mode))


def run_monitor(client: httpx.Client, monitor_id: str) -> dict[str, Any]:
    return request_json(client, "POST", f"/monitors/{monitor_id}/run", {})


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate >30 source batches and run DQ monitor after each batch")
    parser.add_argument("--normal-runs", type=int, default=31, help="Normal insert+monitor cycles before anomaly.")
    parser.add_argument("--anomaly-runs", type=int, default=1, help="Anomaly insert+monitor cycles after normal data.")
    parser.add_argument("--anomaly-mode", choices=ANOMALY_MODES, default="amount_shift")
    parser.add_argument("--hours-per-run", type=int, default=1)
    parser.add_argument("--base-rate", type=float, default=42.0)
    parser.add_argument("--reset-source", action="store_true", help="Truncate and recreate demo_orders history first.")
    parser.add_argument("--history-days", type=int, default=45)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    if args.normal_runs < 31:
        raise ValueError("--normal-runs must be at least 31 to pass the 30-point forecast threshold")
    random.seed(args.seed)

    if args.reset_source:
        with psycopg.connect(SOURCE_DATABASE_URL, autocommit=True) as conn:
            with conn.cursor() as cur:
                ensure_schema(cur)
                inserted = reset_source(cur, args.history_days, args.base_rate)
                print(f"source reset: inserted_history_rows={inserted}")

    with httpx.Client(timeout=120.0) as client:
        wait_for_backend(client)
        connection_id = ensure_connection(client)
        monitor_id = create_monitor(client, connection_id, datetime.now(UTC).strftime("%Y%m%d%H%M%S"))
        print(f"connection_id={connection_id}")
        print(f"monitor_id={monitor_id}")

        baseline_run = run_monitor(client, monitor_id)
        print(f"baseline run: status={baseline_run['status']}, new_rows={baseline_run['new_rows']}")

        for index in range(1, args.normal_runs + 1):
            inserted = append_batch("normal", args.hours_per_run, args.base_rate)
            run = run_monitor(client, monitor_id)
            print(f"normal {index:02d}: inserted={inserted}, status={run['status']}, new_rows={run['new_rows']}")

        for index in range(1, args.anomaly_runs + 1):
            inserted = append_batch(args.anomaly_mode, args.hours_per_run, args.base_rate)
            run = run_monitor(client, monitor_id)
            print(f"anomaly {index:02d}: mode={args.anomaly_mode}, inserted={inserted}, status={run['status']}, new_rows={run['new_rows']}")

        anomalies = request_json(client, "GET", "/anomalies")
        open_anomalies = [item for item in anomalies if item.get("status") != "closed"]
        series = request_json(client, "GET", f"/series?monitor_id={monitor_id}")
        print(f"summary: series={len(series)}, open_anomalies_total={len(open_anomalies)}")


if __name__ == "__main__":
    main()
