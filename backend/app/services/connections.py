from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import encrypt_secret
from app.models import Connection
from app.schemas.api import ConnectionCreate, ConnectionUpdate
from app.services import source_postgres


def list_connections(db: Session) -> list[Connection]:
    return list(db.scalars(select(Connection).order_by(Connection.created_at.desc())))


def get_connection(db: Session, connection_id: str) -> Connection:
    connection = db.get(Connection, connection_id)
    if connection is None:
        raise HTTPException(status_code=404, detail="Подключение не найдено")
    return connection


def create_connection(db: Session, payload: ConnectionCreate) -> Connection:
    connection = Connection(
        name=payload.name,
        db_type=payload.db_type,
        host=payload.host,
        port=payload.port,
        database=payload.database,
        username=payload.username,
        encrypted_password=encrypt_secret(payload.password),
        ssl_params=payload.ssl_params,
    )
    db.add(connection)
    db.commit()
    db.refresh(connection)
    return connection


def update_connection(db: Session, connection_id: str, payload: ConnectionUpdate) -> Connection:
    connection = get_connection(db, connection_id)
    data = payload.model_dump(exclude_unset=True)
    password = data.pop("password", None)
    for field, value in data.items():
        setattr(connection, field, value)
    if password:
        connection.encrypted_password = encrypt_secret(password)
    db.commit()
    db.refresh(connection)
    return connection


def delete_connection(db: Session, connection_id: str) -> None:
    connection = get_connection(db, connection_id)
    if any(monitor.is_active for monitor in connection.monitors):
        raise HTTPException(status_code=409, detail="Нельзя удалить подключение с активными мониторами")
    db.delete(connection)
    db.commit()


def test_and_store(db: Session, connection_id: str) -> dict:
    connection = get_connection(db, connection_id)
    ok, error = source_postgres.test_connection(connection)
    connection.last_check_status = "ok" if ok else "failed"
    connection.last_check_error = error
    db.commit()
    return {"ok": ok, "error": error}
