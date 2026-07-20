from __future__ import annotations

import argparse
import os
import random
from datetime import UTC, datetime, timedelta

import psycopg

from synthetic_orders import GENERATION_MODES, generate_rows, history_start


DATABASE_URL = os.getenv("DEMO_DATABASE_URL", "postgresql://source_owner:source_owner@source-postgres:5432/source")


def insert_rows(cur, rows) -> int:
    if not rows:
        return 0
    cur.executemany(
        "INSERT INTO demo_orders(created_at, amount, status, customer_id) VALUES (%s, %s, %s, %s)",
        [(row.created_at, row.amount, row.status, row.customer_id) for row in rows],
    )
    return len(rows)


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


def ensure_readonly_user(cur) -> None:
    cur.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dq_readonly') THEN
                CREATE USER dq_readonly WITH PASSWORD 'dq_readonly';
            END IF;
        END $$
        """
    )
    cur.execute("GRANT CONNECT ON DATABASE source TO dq_readonly")
    cur.execute("GRANT USAGE ON SCHEMA public TO dq_readonly")
    cur.execute("GRANT SELECT ON ALL TABLES IN SCHEMA public TO dq_readonly")
    cur.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO dq_readonly")


def get_next_start(cur) -> datetime:
    cur.execute("SELECT MAX(created_at) FROM demo_orders")
    max_created_at = cur.fetchone()[0]
    if max_created_at is None:
        return datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    return max_created_at.astimezone(UTC).replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)


def reset_data(cur, days: int, base_rate: float) -> int:
    cur.execute("TRUNCATE TABLE demo_orders RESTART IDENTITY")
    rows = generate_rows(history_start(days), days * 24, base_rate, "normal", late_arrivals_ratio=0.015)
    return insert_rows(cur, rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate realistic synthetic orders in demo source PostgreSQL")
    parser.add_argument("--mode", choices=GENERATION_MODES, default="normal", help="Generation profile. reset recreates history.")
    parser.add_argument("--hours", type=int, default=1, help="How many hourly buckets to append.")
    parser.add_argument("--days", type=int, default=45, help="History length for --mode reset.")
    parser.add_argument("--base-rate", type=float, default=42.0, help="Average hourly order volume before seasonality.")
    parser.add_argument("--late-arrivals-ratio", type=float, default=0.01, help="Share of rows with older created_at.")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducible data.")
    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        with conn.cursor() as cur:
            ensure_schema(cur)
            ensure_readonly_user(cur)
            if args.mode == "reset":
                inserted = reset_data(cur, args.days, args.base_rate)
            else:
                rows = generate_rows(get_next_start(cur), args.hours, args.base_rate, args.mode, args.late_arrivals_ratio)
                inserted = insert_rows(cur, rows)

    print(
        "Demo source data operation completed: "
        f"mode={args.mode}, inserted_rows={inserted}, hours={args.hours}, base_rate={args.base_rate}"
    )


if __name__ == "__main__":
    main()
