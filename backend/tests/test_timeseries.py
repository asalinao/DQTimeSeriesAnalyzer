from app.timeseries.models import compare, forecast_next


def test_rolling_forecast_uses_previous_values_only():
    values = [100.0] * 30
    forecast = forecast_next(values, {"model": "rolling", "window": 30, "k": 3}, min_points=30)

    assert forecast.predicted == 100.0
    assert forecast.lower is not None
    assert forecast.upper is not None

    is_anomaly, reason, severity, absolute, relative = compare(250.0, forecast)
    assert is_anomaly is True
    assert reason == "forecast_bounds"
    assert severity == "critical"
    assert absolute == 150.0
    assert relative == 1.5


def test_static_rules_work_without_history():
    forecast = forecast_next([], {"model": "rolling"}, min_points=30)
    is_anomaly, reason, severity, *_ = compare(0.0, forecast, {"min_value": 1})

    assert is_anomaly is True
    assert reason == "static_min"
    assert severity == "critical"
