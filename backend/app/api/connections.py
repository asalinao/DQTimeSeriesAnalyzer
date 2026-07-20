from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import require_admin
from app.db.session import get_db
from app.schemas.api import ConnectionCreate, ConnectionRead, ConnectionUpdate
from app.services.connections import (
    create_connection,
    delete_connection,
    get_connection,
    list_connections,
    test_and_store,
    update_connection,
)

router = APIRouter(dependencies=[Depends(require_admin)])


@router.post("", response_model=ConnectionRead)
def create(payload: ConnectionCreate, db: Session = Depends(get_db)):
    return create_connection(db, payload)


@router.get("", response_model=list[ConnectionRead])
def list_all(db: Session = Depends(get_db)):
    return list_connections(db)


@router.get("/{connection_id}", response_model=ConnectionRead)
def get_one(connection_id: str, db: Session = Depends(get_db)):
    return get_connection(db, connection_id)


@router.put("/{connection_id}", response_model=ConnectionRead)
def update(connection_id: str, payload: ConnectionUpdate, db: Session = Depends(get_db)):
    return update_connection(db, connection_id, payload)


@router.delete("/{connection_id}", status_code=204)
def delete(connection_id: str, db: Session = Depends(get_db)):
    delete_connection(db, connection_id)


@router.post("/{connection_id}/test")
def test(connection_id: str, db: Session = Depends(get_db)):
    return test_and_store(db, connection_id)
