from dataclasses import dataclass
from statistics import mean, median, pstdev


@dataclass(frozen=True)
class Forecast:
    predicted: float | None
    lower: float | None
    upper: float | None
    deviation_score: float | None
    model_version: str
    details: dict


def _values(history: list[float | None]) -> list[float]:
    return [float(value) for value in history if value is not None]


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


def forecast_next(history: list[float | None], config: dict, min_points: int) -> Forecast:
    model = config.get("model", "rolling")
    if model == "robust_z":
        return robust_z(history, config, min_points)
    if model == "exp_smoothing":
        return exp_smoothing(history, config, min_points)
    if model == "seasonal_naive":
        return seasonal_naive(history, config, min_points)
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
