CREATE TABLE IF NOT EXISTS demo_orders (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL,
    amount NUMERIC,
    status TEXT,
    customer_id BIGINT
);

CREATE INDEX IF NOT EXISTS ix_demo_orders_created_at ON demo_orders(created_at);

INSERT INTO demo_orders(created_at, amount, status, customer_id)
SELECT
    bucket + make_interval(mins => floor(random() * 60)::int, secs => floor(random() * 60)::int),
    ROUND(
        (
            70
            + CASE
                WHEN EXTRACT(HOUR FROM bucket) BETWEEN 11 AND 15 THEN 45
                WHEN EXTRACT(HOUR FROM bucket) BETWEEN 18 AND 22 THEN 35
                WHEN EXTRACT(HOUR FROM bucket) BETWEEN 0 AND 5 THEN -25
                ELSE 0
              END
            + random() * 45
            + CASE WHEN random() < 0.025 THEN random() * 350 ELSE 0 END
        )::numeric,
        2
    ),
    CASE
        WHEN random() < 0.12 THEN 'new'
        WHEN random() < 0.74 THEN 'paid'
        WHEN random() < 0.90 THEN 'shipped'
        WHEN random() < 0.95 THEN 'cancelled'
        WHEN random() < 0.98 THEN 'refunded'
        ELSE 'failed'
    END,
    CASE WHEN random() < 0.18 THEN 1 + floor(random() * 80)::bigint ELSE 1 + floor(random() * 900)::bigint END
FROM generate_series(
    date_trunc('hour', NOW() - interval '45 days'),
    date_trunc('hour', NOW() - interval '1 hour'),
    interval '1 hour'
) AS bucket
CROSS JOIN LATERAL generate_series(
    1,
    GREATEST(
        1,
        (
            20
            + CASE
                WHEN EXTRACT(HOUR FROM bucket) BETWEEN 11 AND 15 THEN 32
                WHEN EXTRACT(HOUR FROM bucket) BETWEEN 18 AND 22 THEN 24
                WHEN EXTRACT(HOUR FROM bucket) BETWEEN 0 AND 5 THEN -14
                ELSE 0
              END
            + CASE WHEN EXTRACT(DOW FROM bucket) IN (0, 6) THEN -10 ELSE 0 END
            + floor(random() * 18)
        )::int
    )
) AS order_no;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dq_readonly') THEN
        CREATE USER dq_readonly WITH PASSWORD 'dq_readonly';
    END IF;
END $$;

GRANT CONNECT ON DATABASE source TO dq_readonly;
GRANT USAGE ON SCHEMA public TO dq_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO dq_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO dq_readonly;
