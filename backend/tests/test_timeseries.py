import pytest

from app.models import SeriesPoint
from app.services.runner import cleaned_history
from app.timeseries.models import compare, evaluate_next, forecast_next


SEASONAL_CYCLE = [100.0, 110.0, 120.0, 110.0, 100.0, 90.0, 80.0, 90.0]


def repeated_cycle(repeats: int = 12) -> list[float]:
    return SEASONAL_CYCLE * repeats


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


def test_quantile_boosting_returns_prediction_interval():
    values = [100.0 + (index % 7) for index in range(80)]
    forecast = forecast_next(
        values,
        {"model": "quantile_boosting", "window": 60, "lags": 5, "n_estimators": 20, "learning_rate": 0.05, "max_depth": 2},
        min_points=20,
    )

    assert forecast.model_version == "quantile_boosting:v1"
    assert forecast.predicted is not None
    assert forecast.lower is not None
    assert forecast.upper is not None
    assert forecast.lower <= forecast.predicted <= forecast.upper


def test_random_forest_returns_prediction_interval():
    values = [100.0 + (index % 7) for index in range(80)]
    forecast = forecast_next(
        values,
        {"model": "random_forest", "window": 60, "lags": 5, "n_estimators": 20, "min_samples_leaf": 1},
        min_points=20,
    )

    assert forecast.model_version == "random_forest:v1"
    assert forecast.predicted is not None
    assert forecast.lower is not None
    assert forecast.upper is not None
    assert forecast.lower <= forecast.predicted <= forecast.upper


def test_isolation_forest_detects_large_spike():
    values = [100.0 + (index % 5) for index in range(80)]
    evaluation = evaluate_next(
        values,
        1000.0,
        {"model": "isolation_forest", "window": 60, "lags": 5, "contamination": 0.05, "n_estimators": 50},
        min_points=20,
    )

    assert evaluation.model_version == "isolation_forest:v1"
    assert evaluation.is_anomaly is True
    assert evaluation.reason in {"isolation_score", "isolation_bounds"}
    assert evaluation.deviation_score is not None


def test_static_rules_override_isolation_forest():
    values = [100.0 + (index % 5) for index in range(80)]
    evaluation = evaluate_next(
        values,
        0.0,
        {"model": "isolation_forest", "window": 60, "lags": 5, "contamination": 0.05, "n_estimators": 20},
        min_points=20,
        rules={"min_value": 1},
    )

    assert evaluation.is_anomaly is True
    assert evaluation.reason == "static_min"
    assert evaluation.severity == "critical"


def test_unknown_model_fails_clearly():
    with pytest.raises(ValueError, match="Unsupported time series model"):
        forecast_next([1.0, 2.0, 3.0], {"model": "missing_model"}, min_points=2)


@pytest.mark.parametrize(
    ("model_config", "model_version"),
    [
        (
            {"model": "quantile_boosting", "window": 96, "lags": 8, "n_estimators": 60, "learning_rate": 0.08, "max_depth": 2},
            "quantile_boosting:v1",
        ),
        (
            {"model": "random_forest", "window": 96, "lags": 8, "n_estimators": 80, "min_samples_leaf": 1},
            "random_forest:v1",
        ),
    ],
)
def test_forecast_models_follow_repeating_cycle(model_config, model_version):
    values = repeated_cycle()
    expected_next = SEASONAL_CYCLE[0]

    normal = evaluate_next(values, expected_next, model_config, min_points=30)
    spike = evaluate_next(values, expected_next + 60.0, model_config, min_points=30)

    assert normal.model_version == model_version
    assert normal.predicted == pytest.approx(expected_next, abs=5.0)
    assert normal.is_anomaly is False
    assert spike.is_anomaly is True
    assert spike.reason == "forecast_bounds"


def test_isolation_forest_accepts_normal_cycle_phase_and_rejects_spike():
    values = repeated_cycle()
    config = {"model": "isolation_forest", "window": 96, "lags": 8, "contamination": 0.03, "n_estimators": 80}
    expected_next = SEASONAL_CYCLE[0]

    normal = evaluate_next(values, expected_next, config, min_points=30)
    spike = evaluate_next(values, expected_next + 60.0, config, min_points=30)

    assert normal.model_version == "isolation_forest:v1"
    assert normal.is_anomaly is False
    assert spike.is_anomaly is True
    assert spike.reason in {"isolation_score", "isolation_bounds"}


def test_cleaned_history_replaces_anomalies_with_predictions():
    chronological_points = [
        SeriesPoint(actual_value=80.0, predicted_value=None, is_anomaly=False),
        SeriesPoint(actual_value=95.0, predicted_value=None, is_anomaly=False),
        SeriesPoint(actual_value=165.0, predicted_value=80.0, is_anomaly=True),
        SeriesPoint(actual_value=95.0, predicted_value=95.0, is_anomaly=False),
    ]

    assert cleaned_history(list(reversed(chronological_points))) == [80.0, 95.0, 80.0, 95.0]


@pytest.mark.parametrize(
    "model_config",
    [
        {"model": "quantile_boosting", "window": 48, "lags": 6, "n_estimators": 70, "learning_rate": 0.08, "max_depth": 2},
        {"model": "random_forest", "window": 48, "lags": 6, "n_estimators": 90, "min_samples_leaf": 1},
        {"model": "isolation_forest", "window": 48, "lags": 6, "contamination": 0.04, "n_estimators": 90},
    ],
)
def test_models_recover_cycle_after_cleaned_spike(model_config):
    cycle = [80.0, 95.0, 115.0, 130.0, 115.0, 95.0]
    history = cycle * 6 + [80.0, 95.0, 115.0, 130.0, 115.0, 95.0]

    normal_next = evaluate_next(history, 80.0, model_config, min_points=30)
    spike = evaluate_next(history, 165.0, model_config, min_points=30)

    assert normal_next.is_anomaly is False
    assert normal_next.predicted == pytest.approx(80.0, abs=8.0)
    assert normal_next.lower is not None
    assert normal_next.upper is not None
    assert normal_next.lower <= 80.0 <= normal_next.upper
    assert spike.is_anomaly is True
