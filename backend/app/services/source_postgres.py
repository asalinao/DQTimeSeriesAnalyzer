from typing import Any

from app.core.security import decrypt_secret
from app.models import Connection
from app.services.sql_safety import build_checkpoint_sql


def _connect(connection: Connection, timeout: int = 10):
    import psycopg

    password = decrypt_secret(connection.encrypted_password)
    sslmode = connection.ssl_params.get("sslmode", "prefer") if connection.ssl_params else "prefer"
    return psycopg.connect(
        host=connection.host,
        port=connection.port,
        dbname=connection.database,
        user=connection.username,
        password=password,
        connect_timeout=timeout,
        sslmode=sslmode,
        autocommit=True,
    )


def test_connection(connection: Connection) -> tuple[bool, str | None]:
    try:
        with _connect(connection, timeout=5) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        return True, None
    except Exception as exc:
        return False, str(exc)


def fetch_current_checkpoint(connection: Connection, schema_name: str, table_name: str, checkpoint_column: str) -> str | None:
    sql = build_checkpoint_sql(schema_name, table_name, checkpoint_column)
    with _connect(connection) as conn, conn.cursor() as cur:
        cur.execute(sql)
        row = cur.fetchone()
        return None if not row else (None if row[0] is None else str(row[0]))


def execute_aggregate(connection: Connection, sql: str, params: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
    with _connect(connection, timeout=timeout_seconds) as conn, conn.cursor() as cur:
        cur.execute(f"SET statement_timeout = {int(timeout_seconds * 1000)}")
        cur.execute(sql, params)
        row = cur.fetchone()
        if row is None:
            return {}
        return {desc.name: value for desc, value in zip(cur.description, row, strict=False)}
