import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("ENCRYPTION_KEY", "test-key")
    monkeypatch.setenv("ADMIN_TOKEN", "change-me")

    from app.db import session as db_session

    db_session.engine.dispose()
    db_session.engine = db_session.create_engine(
        os.environ["DATABASE_URL"],
        future=True,
        connect_args={"check_same_thread": False},
    )
    db_session.SessionLocal.configure(bind=db_session.engine)

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
