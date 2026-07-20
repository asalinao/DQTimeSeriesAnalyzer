from itertools import count


def test_create_monitor_run_and_anomaly(client, monkeypatch):
    from app.services import source_postgres

    checkpoints = count(1)

    def fake_checkpoint(*args, **kwargs):
        return str(next(checkpoints))

    values = [100.0] * 30 + [250.0]

    def fake_aggregate(*args, **kwargs):
        value = values.pop(0)
        return {
            "table__row_count": 10,
            "amount__avg": value,
        }

    monkeypatch.setattr(source_postgres, "test_connection", lambda connection: (True, None))
    monkeypatch.setattr(source_postgres, "fetch_current_checkpoint", fake_checkpoint)
    monkeypatch.setattr(source_postgres, "execute_aggregate", fake_aggregate)

    connection = client.post(
        "/api/v1/connections",
        json={
            "name": "Demo",
            "host": "localhost",
            "port": 5432,
            "database": "demo",
            "username": "readonly",
            "password": "secret",
        },
    ).json()
    assert "encrypted_password" not in connection

    assert client.post(f"/api/v1/connections/{connection['id']}/test").json()["ok"] is True

    monitor = client.post(
        "/api/v1/monitors",
        json={
            "name": "Orders quality",
            "connection_id": connection["id"],
            "schema_name": "public",
            "table_name": "orders",
            "checkpoint_column": "created_at",
            "selected_metrics": {"__table__": ["row_count"], "amount": ["avg"]},
            "model_config": {"model": "rolling", "window": 30, "k": 3},
            "static_rules": {"row_count": {"min_value": 1}},
        },
    ).json()

    monitor = client.put(
        f"/api/v1/monitors/{monitor['id']}",
        json={
            "name": "Orders quality edited",
            "schedule_cron": "0 */2 * * *",
            "timezone": "Europe/Moscow",
            "is_active": True,
            "query_timeout_seconds": 30,
        },
    ).json()
    assert monitor["name"] == "Orders quality edited"
    assert monitor["schedule_cron"] == "0 */2 * * *"
    assert monitor["timezone"] == "Europe/Moscow"
    assert monitor["is_active"] is True

    for _ in range(30):
        assert client.post(f"/api/v1/monitors/{monitor['id']}/run").json()["status"] == "success"

    anomaly_run = client.post(f"/api/v1/monitors/{monitor['id']}/run").json()
    assert anomaly_run["status"] == "success"

    anomalies = client.get("/api/v1/anomalies").json()
    assert len(anomalies) == 1
    assert anomalies[0]["severity"] == "critical"

    series = client.get(f"/api/v1/series?monitor_id={monitor['id']}").json()
    assert len(series) == 2
    points = client.get(f"/api/v1/series/{series[0]['id']}/points").json()
    assert points

    assert client.delete(f"/api/v1/monitors/{monitor['id']}").status_code == 204
    assert client.get(f"/api/v1/monitors/{monitor['id']}").status_code == 404
    assert client.get(f"/api/v1/series?monitor_id={monitor['id']}").json() == []


def test_invalid_monitor_cron_is_rejected(client):
    connection = client.post(
        "/api/v1/connections",
        json={
            "name": "Source",
            "host": "localhost",
            "port": 5432,
            "database": "source",
            "username": "readonly",
            "password": "secret",
        },
    ).json()

    response = client.post(
        "/api/v1/monitors",
        json={
            "name": "Bad schedule",
            "connection_id": connection["id"],
            "schema_name": "public",
            "table_name": "orders",
            "checkpoint_column": "created_at",
            "schedule_cron": "every five minutes",
            "selected_metrics": {"__table__": ["row_count"]},
        },
    )

    assert response.status_code == 422
