from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, median, pstdev


@dataclass
class Forecast:
    predicted: float | None
    lower: float | None
    upper: float | None
    deviation_score: float | None
    model_version: str
    details: dict


def _clean(values: list[float | None]) -> list[float]:
    return [float(v) for v in values if v is not None]


def rolling_statistics(values: list[float | None], config: dict, min_points: int) -> Forecast:
    valid = _clean(values)
    window = int(config.get("window", min(30, max(len(valid), 1))))
    k = float(config.get("k", 3.0))
    min_std = float(config.get("min_std", 0.000001))
    train = valid[-window:]
    if len(train) < min_points:
        return Forecast(None, None, None, None, "rolling:v1", {"training_points": len(train)})
    avg = mean(train)
    std = max(pstdev(train), min_std)
    return Forecast(avg, avg - k * std, avg + k * std, None, "rolling:v1", {"training_points": len(train), "std": std, "k": k})


def robust_z_score(values: list[float | None], config: dict, min_points: int) -> Forecast:
    valid = _clean(values)
    window = int(config.get("window", min(30, max(len(valid), 1))))
    threshold = float(config.get("threshold", 3.5))
    train = valid[-window:]
    if len(train) < min_points:
        return Forecast(None, None, None, None, "robust_z:v1", {"training_points": len(train)})
    med = median(train)
    deviations = [abs(v - med) for v in train]
    mad = max(median(deviations), 0.000001)
    spread = threshold * 1.4826 * mad
    return Forecast(med, med - spread, med + spread, None, "robust_z:v1", {"training_points": len(train), "mad": mad})


def exponential_smoothing(values: list[float | None], config: dict, min_points: int) -> Forecast:
    valid = _clean(values)
    if len(valid) < min_points:
        return Forecast(None, None, None, None, "exp_smoothing:v1", {"training_points": len(valid)})
    alpha = float(config.get("alpha", 0.35))
    smoothed = valid[0]
    residuals: list[float] = []
    for value in valid[1:]:
        residuals.append(value - smoothed)
        smoothed = alpha * value + (1 - alpha) * smoothed
    spread = float(config.get("k", 3.0)) * max(pstdev(residuals) if residuals else 0.0, 0.000001)
    return Forecast(smoothed, smoothed - spread, smoothed + spread, None, "exp_smoothing:v1", {"training_points": len(valid), "alpha": alpha})


def seasonal_naive(values: list[float | None], config: dict, min_points: int) -> Forecast:
    valid = _clean(values)
    season_length = int(config.get("season_length", 24))
    required = max(min_points, season_length * 2)
    if len(valid) < required:
        return Forecast(None, None, None, None, "seasonal_naive:v1", {"training_points": len(valid), "required": required})
    predicted = valid[-season_length]
    tolerance = float(config.get("tolerance", 0.2))
    spread = max(abs(predicted) * tolerance, float(config.get("min_spread", 0.000001)))
    return Forecast(predicted, predicted - spread, predicted + spread, None, "seasonal_naive:v1", {"training_points": len(valid), "season_length": season_length})


def forecast_next(values: list[float | None], config: dict, min_points: int) -> Forecast:
    model = config.get("model", "rolling")
    if model == "robust_z":
        return robust_z_score(values, config, min_points)
    if model == "exp_smoothing":
        return exponential_smoothing(values, config, min_points)
    if model == "seasonal_naive":
        return seasonal_naive(values, config, min_points)
    return rolling_statistics(values, config, min_points)


def compare(actual: float | None, forecast: Forecast, rules: dict | None = None) -> tuple[bool, str | None, str, float | None, float | None]:
    if actual is None:
        if rules and rules.get("forbid_null"):
            return True, "forbid_null", "critical", None, None
        return False, None, "info", None, None

    if rules:
        min_value = rules.get("min_value")
        max_value = rules.get("max_value")
        if min_value is not None and actual < float(min_value):
            return True, "static_min", "critical", abs(float(min_value) - actual), None
        if max_value is not None and actual > float(max_value):
            return True, "static_max", "critical", abs(actual - float(max_value)), None

    if forecast.lower is None or forecast.upper is None:
        return False, None, "info", None, None
    if actual < forecast.lower or actual > forecast.upper:
        predicted = forecast.predicted if forecast.predicted is not None else (forecast.lower + forecast.upper) / 2
        absolute = abs(actual - predicted)
        relative = absolute / abs(predicted) if predicted else None
        severity = "critical" if relative is not None and relative >= 0.5 else "warning"
        return True, "forecast_bounds", severity, absolute, relative
    return False, None, "info", None, None
