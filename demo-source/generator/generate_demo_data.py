from __future__ import annotations

import argparse
import os
import random
from datetime import UTC, datetime, timedelta

import psycopg

from synthetic_orders import GENERATION_MODES, generate_rows, history_start


DATABASE_URL = os.getenv("DEMO_DATABASE_URL", "postgresql://source_owner:source_owner@source-postgres:5432/source")


def ensure_schema(cursor) -> None:
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


def ensure_readonly_user(cursor) -> None:
    cursor.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dq_readonly') THEN
                CREATE USER dq_readonly WITH PASSWORD 'dq_readonly';
            END IF;
        END $$
        """
    )
    cursor.execute("GRANT CONNECT ON DATABASE source TO dq_readonly")
    cursor.execute("GRANT USAGE ON SCHEMA public TO dq_readonly")
    cursor.execute("GRANT SELECT ON ALL TABLES IN SCHEMA public TO dq_readonly")
    cursor.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO dq_readonly")


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


def run(args: argparse.Namespace) -> int:
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn, conn.cursor() as cursor:
        ensure_schema(cursor)
        ensure_readonly_user(cursor)
        if args.mode == "reset":
            cursor.execute("TRUNCATE TABLE demo_orders RESTART IDENTITY")
            rows = generate_rows(history_start(args.days), args.days * 24, args.base_rate, "normal", late_arrivals_ratio=0.015)
        else:
            rows = generate_rows(next_start(cursor), args.hours, args.base_rate, args.mode, args.late_arrivals_ratio)
        return insert_rows(cursor, rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate realistic synthetic orders in demo source PostgreSQL")
    parser.add_argument("--mode", choices=GENERATION_MODES, default="normal")
    parser.add_argument("--hours", type=int, default=1)
    parser.add_argument("--days", type=int, default=45)
    parser.add_argument("--base-rate", type=float, default=42.0)
    parser.add_argument("--late-arrivals-ratio", type=float, default=0.01)
    parser.add_argument("--seed", type=int, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.seed is not None:
        random.seed(args.seed)
    inserted = run(args)
    print(f"Demo source data operation completed: mode={args.mode}, inserted_rows={inserted}, hours={args.hours}, base_rate={args.base_rate}")


if __name__ == "__main__":
    main()
