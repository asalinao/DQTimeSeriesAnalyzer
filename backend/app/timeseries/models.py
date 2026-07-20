from dataclasses import dataclass
from statistics import mean, median, pstdev
from typing import Any


SUPPORTED_MODELS = {
    "rolling",
    "robust_z",
    "exp_smoothing",
    "seasonal_naive",
    "quantile_boosting",
    "random_forest",
    "isolation_forest",
}


@dataclass(frozen=True)
class Forecast:
    predicted: float | None
    lower: float | None
    upper: float | None
    deviation_score: float | None
    model_version: str
    details: dict


@dataclass(frozen=True)
class Evaluation:
    predicted: float | None
    lower: float | None
    upper: float | None
    is_anomaly: bool
    reason: str | None
    severity: str
    absolute_deviation: float | None
    relative_deviation: float | None
    deviation_score: float | None
    model_version: str
    details: dict


def _values(history: list[float | None]) -> list[float]:
    return [float(value) for value in history if value is not None]


def _model_name(config: dict) -> str:
    model = str(config.get("model", "rolling"))
    if model not in SUPPORTED_MODELS:
        raise ValueError(f"Unsupported time series model: {model}")
    return model


def _int_config(config: dict, name: str, default: int, minimum: int | None = None, maximum: int | None = None) -> int:
    try:
        value = int(config.get(name, default))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{name} must be <= {maximum}")
    return value


def _optional_int_config(config: dict, name: str, minimum: int | None = None, maximum: int | None = None) -> int | None:
    value = config.get(name)
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer or null") from exc
    if minimum is not None and parsed < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    if maximum is not None and parsed > maximum:
        raise ValueError(f"{name} must be <= {maximum}")
    return parsed


def _float_config(config: dict, name: str, default: float, minimum: float | None = None, maximum: float | None = None) -> float:
    try:
        value = float(config.get(name, default))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a number") from exc
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{name} must be <= {maximum}")
    return value


def _quantiles(config: dict) -> tuple[float, float]:
    lower = _float_config(config, "lower_quantile", 0.05, 0.0, 1.0)
    upper = _float_config(config, "upper_quantile", 0.95, 0.0, 1.0)
    if lower <= 0 or upper >= 1 or lower >= upper:
        raise ValueError("quantiles must satisfy 0 < lower_quantile < upper_quantile < 1")
    return lower, upper


def _ml_training_values(values: list[float], config: dict, min_points: int) -> tuple[list[float], int, int]:
    window = _int_config(config, "window", 120, minimum=2, maximum=10000)
    lags = _int_config(config, "lags", 12, minimum=1, maximum=512)
    train = values[-window:]
    required_values = max(min_points + lags, lags + 2)
    return train, lags, required_values


def _lagged_dataset(values: list[float], lags: int) -> tuple[list[list[float]], list[float]]:
    features: list[list[float]] = []
    targets: list[float] = []
    for index in range(lags, len(values)):
        features.append(values[index - lags : index])
        targets.append(values[index])
    return features, targets


def _empty_forecast(model_version: str, training_points: int, **details: Any) -> Forecast:
    return Forecast(None, None, None, None, model_version, {"training_points": training_points, **details})


def _percentile(values: list[float], quantile: float) -> float:
    if not values:
        raise ValueError("Cannot compute percentile for an empty list")
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(ordered) - 1)
    fraction = position - lower_index
    return ordered[lower_index] * (1 - fraction) + ordered[upper_index] * fraction


def _ordered_bounds(*values: float) -> tuple[float, float]:
    return min(values), max(values)


def _spread_floor(predicted: float, config: dict) -> float:
    ratio = _float_config(config, "residual_floor_ratio", 0.03, minimum=0.0, maximum=1.0)
    min_spread = _float_config(config, "min_spread", 0.000001, minimum=0.0)
    return max(min_spread, abs(predicted) * ratio)


def _residual_interval(predicted: float, training_predictions: list[float], targets: list[float], config: dict) -> tuple[float, float, dict]:
    lower_quantile, upper_quantile = _quantiles(config)
    residuals = [target - training_prediction for target, training_prediction in zip(targets, training_predictions, strict=True)]
    lower_residual = _percentile(residuals, lower_quantile)
    upper_residual = _percentile(residuals, upper_quantile)
    lower, upper = _ordered_bounds(predicted + lower_residual, predicted, predicted + upper_residual)
    floor = _spread_floor(predicted, config)
    if upper - lower < floor * 2:
        lower = predicted - floor
        upper = predicted + floor
    return (
        lower,
        upper,
        {
            "interval_method": "residual_quantile",
            "residual_floor": floor,
            "lower_residual": lower_residual,
            "upper_residual": upper_residual,
        },
    )


def rolling(history: list[float | None], config: dict, min_points: int) -> Forecast:
    values = _values(history)
    window = int(config.get("window", 30))
    train = values[-window:]
    if len(train) < min_points:
        return Forecast(None, None, None, None, "rolling:v1", {"training_points": len(train)})
    k = float(config.get("k", 3.0))
    std = max(pstdev(train), float(config.get("min_std", 0.000001)))
    avg = mean(train)
    return Forecast(avg, avg - k * std, avg + k * std, None, "rolling:v1", {"training_points": len(train), "std": std, "k": k})


def robust_z(history: list[float | None], config: dict, min_points: int) -> Forecast:
    values = _values(history)
    window = int(config.get("window", 30))
    train = values[-window:]
    if len(train) < min_points:
        return Forecast(None, None, None, None, "robust_z:v1", {"training_points": len(train)})
    center = median(train)
    mad = max(median(abs(value - center) for value in train), 0.000001)
    spread = float(config.get("threshold", 3.5)) * 1.4826 * mad
    return Forecast(center, center - spread, center + spread, None, "robust_z:v1", {"training_points": len(train), "mad": mad})


def exp_smoothing(history: list[float | None], config: dict, min_points: int) -> Forecast:
    values = _values(history)
    if len(values) < min_points:
        return Forecast(None, None, None, None, "exp_smoothing:v1", {"training_points": len(values)})
    alpha = float(config.get("alpha", 0.35))
    smoothed = values[0]
    residuals: list[float] = []
    for value in values[1:]:
        residuals.append(value - smoothed)
        smoothed = alpha * value + (1 - alpha) * smoothed
    spread = float(config.get("k", 3.0)) * max(pstdev(residuals) if residuals else 0.0, 0.000001)
    return Forecast(smoothed, smoothed - spread, smoothed + spread, None, "exp_smoothing:v1", {"training_points": len(values), "alpha": alpha})


def seasonal_naive(history: list[float | None], config: dict, min_points: int) -> Forecast:
    values = _values(history)
    season_length = int(config.get("season_length", 24))
    required = max(min_points, season_length * 2)
    if len(values) < required:
        return Forecast(None, None, None, None, "seasonal_naive:v1", {"training_points": len(values), "required": required})
    predicted = values[-season_length]
    spread = max(abs(predicted) * float(config.get("tolerance", 0.2)), float(config.get("min_spread", 0.000001)))
    return Forecast(predicted, predicted - spread, predicted + spread, None, "seasonal_naive:v1", {"training_points": len(values), "season_length": season_length})


def quantile_boosting(history: list[float | None], config: dict, min_points: int) -> Forecast:
    from sklearn.ensemble import GradientBoostingRegressor

    values = _values(history)
    train, lags, required_values = _ml_training_values(values, config, min_points)
    if len(train) < required_values:
        return _empty_forecast("quantile_boosting:v1", len(train), required=required_values, lags=lags)

    features, targets = _lagged_dataset(train, lags)
    if len(targets) < min_points:
        return _empty_forecast("quantile_boosting:v1", len(train), training_rows=len(targets), required_rows=min_points, lags=lags)

    lower_quantile, upper_quantile = _quantiles(config)
    n_estimators = _int_config(config, "n_estimators", 100, minimum=10, maximum=500)
    learning_rate = _float_config(config, "learning_rate", 0.05, minimum=0.0001, maximum=1.0)
    max_depth = _int_config(config, "max_depth", 3, minimum=1, maximum=16)
    random_state = _int_config(config, "random_state", 42)
    next_features = [train[-lags:]]

    model = GradientBoostingRegressor(
        loss="squared_error",
        n_estimators=n_estimators,
        learning_rate=learning_rate,
        max_depth=max_depth,
        random_state=random_state,
    )
    model.fit(features, targets)
    predicted = float(model.predict(next_features)[0])
    training_predictions = [float(value) for value in model.predict(features)]
    lower, upper, interval_details = _residual_interval(predicted, training_predictions, targets, config)
    return Forecast(
        predicted,
        lower,
        upper,
        None,
        "quantile_boosting:v1",
        {
            "training_points": len(train),
            "training_rows": len(targets),
            "lags": lags,
            "lower_quantile": lower_quantile,
            "upper_quantile": upper_quantile,
            "n_estimators": n_estimators,
            "learning_rate": learning_rate,
            "max_depth": max_depth,
            **interval_details,
        },
    )


def random_forest(history: list[float | None], config: dict, min_points: int) -> Forecast:
    from sklearn.ensemble import RandomForestRegressor

    values = _values(history)
    train, lags, required_values = _ml_training_values(values, config, min_points)
    if len(train) < required_values:
        return _empty_forecast("random_forest:v1", len(train), required=required_values, lags=lags)

    features, targets = _lagged_dataset(train, lags)
    if len(targets) < min_points:
        return _empty_forecast("random_forest:v1", len(train), training_rows=len(targets), required_rows=min_points, lags=lags)

    lower_quantile, upper_quantile = _quantiles(config)
    n_estimators = _int_config(config, "n_estimators", 200, minimum=10, maximum=500)
    max_depth = _optional_int_config(config, "max_depth", minimum=1, maximum=64)
    min_samples_leaf = _int_config(config, "min_samples_leaf", 2, minimum=1, maximum=128)
    random_state = _int_config(config, "random_state", 42)
    next_features = [train[-lags:]]
    model = RandomForestRegressor(
        n_estimators=n_estimators,
        max_depth=max_depth,
        min_samples_leaf=min_samples_leaf,
        random_state=random_state,
    )
    model.fit(features, targets)
    predicted = float(model.predict(next_features)[0])
    training_predictions = [float(value) for value in model.predict(features)]
    lower, upper, interval_details = _residual_interval(predicted, training_predictions, targets, config)
    return Forecast(
        predicted,
        lower,
        upper,
        None,
        "random_forest:v1",
        {
            "training_points": len(train),
            "training_rows": len(targets),
            "lags": lags,
            "lower_quantile": lower_quantile,
            "upper_quantile": upper_quantile,
            "n_estimators": n_estimators,
            "max_depth": max_depth,
            "min_samples_leaf": min_samples_leaf,
            **interval_details,
        },
    )


def empirical_range(history: list[float | None], config: dict, min_points: int, model_version: str) -> Forecast:
    values = _values(history)
    window = _int_config(config, "window", 120, minimum=2, maximum=10000)
    lower_quantile, upper_quantile = _quantiles(config) if "lower_quantile" in config or "upper_quantile" in config else (0.05, 0.95)
    train = values[-window:]
    if len(train) < min_points:
        return _empty_forecast(model_version, len(train), required=min_points)

    lags = _int_config(config, "lags", 12, minimum=1, maximum=512)
    if len(train) >= max(min_points + lags, lags + 2):
        targets = train[lags:]
        training_predictions = train[:-lags]
        predicted = train[-lags]
        lower, upper, interval_details = _residual_interval(predicted, training_predictions, targets, config)
        details = {
            "training_points": len(train),
            "training_rows": len(targets),
            "lags": lags,
            "lower_quantile": lower_quantile,
            "upper_quantile": upper_quantile,
            "summary": "seasonal-lag display forecast; isolation score is the anomaly decision",
            **interval_details,
        }
    else:
        predicted = median(train)
        lower, upper = _ordered_bounds(_percentile(train, lower_quantile), predicted, _percentile(train, upper_quantile))
        details = {
            "training_points": len(train),
            "lags": lags,
            "lower_quantile": lower_quantile,
            "upper_quantile": upper_quantile,
            "summary": "empirical fallback bounds for display; isolation score is the anomaly decision",
        }
    return Forecast(
        predicted,
        lower,
        upper,
        None,
        model_version,
        details,
    )


def forecast_next(history: list[float | None], config: dict, min_points: int) -> Forecast:
    model = _model_name(config)
    if model == "robust_z":
        return robust_z(history, config, min_points)
    if model == "exp_smoothing":
        return exp_smoothing(history, config, min_points)
    if model == "seasonal_naive":
        return seasonal_naive(history, config, min_points)
    if model == "quantile_boosting":
        return quantile_boosting(history, config, min_points)
    if model == "random_forest":
        return random_forest(history, config, min_points)
    if model == "isolation_forest":
        return empirical_range(history, config, min_points, "isolation_forest:v1")
    return rolling(history, config, min_points)


def compare(actual: float | None, forecast: Forecast, rules: dict | None = None) -> tuple[bool, str | None, str, float | None, float | None]:
    if actual is None:
        return (True, "forbid_null", "critical", None, None) if rules and rules.get("forbid_null") else (False, None, "info", None, None)

    if rules:
        min_value = rules.get("min_value")
        max_value = rules.get("max_value")
        if min_value is not None and actual < float(min_value):
            return True, "static_min", "critical", abs(float(min_value) - actual), None
        if max_value is not None and actual > float(max_value):
            return True, "static_max", "critical", abs(actual - float(max_value)), None

    if forecast.lower is None or forecast.upper is None:
        return False, None, "info", None, None
    if forecast.lower <= actual <= forecast.upper:
        return False, None, "info", None, None

    predicted = forecast.predicted if forecast.predicted is not None else (forecast.lower + forecast.upper) / 2
    absolute = abs(actual - predicted)
    relative = absolute / abs(predicted) if predicted else None
    severity = "critical" if relative is not None and relative >= 0.5 else "warning"
    return True, "forecast_bounds", severity, absolute, relative


def evaluate_next(history: list[float | None], actual: float | None, config: dict, min_points: int, rules: dict | None = None) -> Evaluation:
    if _model_name(config) == "isolation_forest":
        return evaluate_isolation_forest(history, actual, config, min_points, rules)

    forecast = forecast_next(history, config, min_points)
    is_anomaly, reason, severity, absolute, relative = compare(actual, forecast, rules)
    return Evaluation(
        forecast.predicted,
        forecast.lower,
        forecast.upper,
        is_anomaly,
        reason,
        severity,
        absolute,
        relative,
        forecast.deviation_score if forecast.deviation_score is not None else relative,
        forecast.model_version,
        forecast.details,
    )


def evaluate_isolation_forest(history: list[float | None], actual: float | None, config: dict, min_points: int, rules: dict | None = None) -> Evaluation:
    from sklearn.ensemble import IsolationForest

    values = _values(history)
    forecast = empirical_range(history, config, min_points, "isolation_forest:v1")
    static_anomaly, static_reason, static_severity, static_absolute, static_relative = compare_static_rules(actual, rules)
    if static_anomaly:
        return Evaluation(
            forecast.predicted,
            forecast.lower,
            forecast.upper,
            True,
            static_reason,
            static_severity,
            static_absolute,
            static_relative,
            static_relative,
            forecast.model_version,
            forecast.details,
        )
    if actual is None:
        return Evaluation(forecast.predicted, forecast.lower, forecast.upper, False, None, "info", None, None, None, forecast.model_version, forecast.details)

    train, lags, required_values = _ml_training_values(values, config, min_points)
    training_windows = len(train) - lags
    if len(train) < required_values or training_windows < min_points:
        details = {**forecast.details, "training_points": len(train), "training_windows": max(training_windows, 0), "required": required_values, "lags": lags}
        return Evaluation(forecast.predicted, forecast.lower, forecast.upper, False, None, "info", None, None, None, forecast.model_version, details)

    samples = [train[index - lags : index + 1] for index in range(lags, len(train))]
    current_sample = train[-lags:] + [float(actual)]
    contamination = _float_config(config, "contamination", 0.03, minimum=0.0001, maximum=0.49)
    n_estimators = _int_config(config, "n_estimators", 100, minimum=10, maximum=500)
    random_state = _int_config(config, "random_state", 42)
    detector = IsolationForest(n_estimators=n_estimators, contamination=contamination, random_state=random_state)
    detector.fit(samples)
    prediction = int(detector.predict([current_sample])[0])
    decision_score = float(detector.decision_function([current_sample])[0])
    deviation_score = max(-decision_score, 0.0)
    predicted = forecast.predicted
    absolute = abs(float(actual) - predicted) if predicted is not None else None
    relative = absolute / abs(predicted) if absolute is not None and predicted else None
    bounds_anomaly = forecast.lower is not None and forecast.upper is not None and not (forecast.lower <= float(actual) <= forecast.upper)
    is_anomaly = prediction == -1 or bounds_anomaly
    severity = "critical" if is_anomaly and ((relative is not None and relative >= 0.5) or decision_score <= -0.05) else "warning" if is_anomaly else "info"
    details = {
        **forecast.details,
        "training_points": len(train),
        "training_windows": len(samples),
        "lags": lags,
        "contamination": contamination,
        "n_estimators": n_estimators,
        "decision_score": decision_score,
        "deviation_score": deviation_score,
        "isolation_prediction": prediction,
        "bounds_guard_triggered": bounds_anomaly and prediction != -1,
    }
    return Evaluation(
        predicted,
        forecast.lower,
        forecast.upper,
        is_anomaly,
        "isolation_score" if prediction == -1 else "isolation_bounds" if is_anomaly else None,
        severity,
        absolute if is_anomaly else None,
        relative if is_anomaly else None,
        deviation_score,
        forecast.model_version,
        details,
    )


def compare_static_rules(actual: float | None, rules: dict | None = None) -> tuple[bool, str | None, str, float | None, float | None]:
    if actual is None:
        return (True, "forbid_null", "critical", None, None) if rules and rules.get("forbid_null") else (False, None, "info", None, None)
    if not rules:
        return False, None, "info", None, None
    min_value = rules.get("min_value")
    max_value = rules.get("max_value")
    if min_value is not None and actual < float(min_value):
        return True, "static_min", "critical", abs(float(min_value) - actual), None
    if max_value is not None and actual > float(max_value):
        return True, "static_max", "critical", abs(actual - float(max_value)), None
    return False, None, "info", None, None
