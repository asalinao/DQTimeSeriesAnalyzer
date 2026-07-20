import pytest

from app.services.sql_safety import UnsafeSqlError, build_aggregate_sql, ensure_identifier


def test_rejects_invalid_identifier():
    with pytest.raises(UnsafeSqlError):
        ensure_identifier("orders;DROP", "table")


def test_builds_parameterized_auto_checkpoint_sql():
    sql, specs = build_aggregate_sql(
        "public",
        "orders",
        "created_at",
        {"__table__": ["row_count"], "amount": ["avg", "null_ratio"]},
        "2026-07-19T00:00:00Z",
    )

    assert '"public"."orders"' in sql
    assert "%(previous_checkpoint)s" in sql
    assert "%(current_checkpoint)s" in sql
    assert "COUNT(*)" in sql
    assert [spec.metric_name for spec in specs] == ["row_count", "avg", "null_ratio"]
