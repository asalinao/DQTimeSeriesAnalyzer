from typing import Any

from app.core.security import decrypt_secret
from app.models import Connection
from app.services.sql_safety import build_checkpoint_sql


def connect(connection: Connection, timeout: int = 10):
    import psycopg

    sslmode = (connection.ssl_params or {}).get("sslmode", "prefer")
    return psycopg.connect(
        host=connection.host,
        port=connection.port,
        dbname=connection.database,
        user=connection.username,
        password=decrypt_secret(connection.encrypted_password),
        connect_timeout=timeout,
        sslmode=sslmode,
        autocommit=True,
    )


def test_connection(connection: Connection) -> tuple[bool, str | None]:
    try:
        with connect(connection, timeout=5) as conn, conn.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return True, None
    except Exception as exc:
        return False, str(exc)


def fetch_current_checkpoint(connection: Connection, schema_name: str, table_name: str, checkpoint_column: str) -> str | None:
    with connect(connection) as conn, conn.cursor() as cursor:
        cursor.execute(build_checkpoint_sql(schema_name, table_name, checkpoint_column))
        row = cursor.fetchone()
    return None if not row or row[0] is None else str(row[0])


def execute_aggregate(connection: Connection, sql: str, params: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
    with connect(connection, timeout=timeout_seconds) as conn, conn.cursor() as cursor:
        cursor.execute(f"SET statement_timeout = {int(timeout_seconds * 1000)}")
        cursor.execute(sql, params)
        row = cursor.fetchone()
        if row is None:
            return {}
        return {column.name: value for column, value in zip(cursor.description, row, strict=False)}
