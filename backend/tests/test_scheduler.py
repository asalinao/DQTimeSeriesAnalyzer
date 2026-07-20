from datetime import datetime, timezone

from app.models import Monitor


def test_cron_schedule_waits_until_next_matching_minute(monkeypatch):
    from app.scheduler import runner

    monitor = Monitor(
        id="monitor-id",
        name="Orders quality",
        connection_id="connection-id",
        schema_name="public",
        table_name="orders",
        checkpoint_column="created_at",
        schedule_cron="*/5 * * * *",
        timezone="UTC",
        is_active=True,
        created_at=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
    )

    monkeypatch.setattr(runner, "latest_run_at", lambda _monitor_id: None)

    assert runner.is_due(monitor, datetime(2026, 1, 1, 12, 4, 59, tzinfo=timezone.utc)) is False
    assert runner.is_due(monitor, datetime(2026, 1, 1, 12, 5, tzinfo=timezone.utc)) is True


def test_cron_schedule_uses_monitor_timezone(monkeypatch):
    from app.scheduler import runner

    monitor = Monitor(
        id="monitor-id",
        name="Orders quality",
        connection_id="connection-id",
        schema_name="public",
        table_name="orders",
        checkpoint_column="created_at",
        schedule_cron="0 9 * * *",
        timezone="Europe/Moscow",
        is_active=True,
        created_at=datetime(2026, 1, 1, 5, 0, tzinfo=timezone.utc),
    )

    monkeypatch.setattr(runner, "latest_run_at", lambda _monitor_id: None)

    assert runner.is_due(monitor, datetime(2026, 1, 1, 5, 59, tzinfo=timezone.utc)) is False
    assert runner.is_due(monitor, datetime(2026, 1, 1, 6, 0, tzinfo=timezone.utc)) is True
