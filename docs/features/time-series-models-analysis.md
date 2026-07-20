# Feature analysis: ML models for time series anomaly detection

## Goal

Add three model options to the current MVP:

- `quantile_boosting`
- `random_forest`
- `isolation_forest`

The feature should improve anomaly detection for non-linear time series patterns while preserving the current MVP flow: monitor run -> aggregate metrics -> series point -> forecast/bounds -> anomaly -> UI/webhook.

## Current State

The backend already has a small model boundary in `backend/app/timeseries/models.py`:

- `forecast_next(history, config, min_points)` selects a model by `model_config.model`.
- Every model returns `Forecast(predicted, lower, upper, deviation_score, model_version, details)`.
- `compare(actual, forecast, rules)` applies static rules first, then marks an anomaly when `actual` is outside `lower`/`upper`.
- `backend/app/services/runner.py` calls forecasting before inserting each `SeriesPoint`.

Existing supported models are:

- `rolling`
- `robust_z`
- `exp_smoothing`
- `seasonal_naive`

Data storage is already sufficient for prediction intervals:

- `series_points.predicted_value`
- `series_points.lower_bound`
- `series_points.upper_bound`
- `series_points.deviation_score`
- `series_points.model_version`
- `series_points.model_details`

No database migration is required for basic support.

## Important MVP Constraint

Current code stores model config in two places:

- monitor-level: `monitors.model_config`
- series-level: `series.model_config`

When a series is first created, `runner.get_or_create_series()` copies `monitor.model_config` into `series.model_config`. Later monitor edits may not affect existing series because `forecast_for_series()` prefers `series.model_config`.

Decision needed for this feature:

- Recommended for MVP: use monitor config as the source of truth until per-series model editing exists.
- Implementation option: change `forecast_for_series()` to merge `monitor.model_config` with `series.model_config` only when series-level overrides are explicitly present.
- Alternative: when a monitor is updated, propagate the new `model_config` to existing series. This is simpler but makes future per-series overrides harder.

## Model Fit

### `quantile_boosting`

Purpose:

- Predict an expected value plus lower/upper quantiles.
- Good for skewed metric distributions where mean/std bounds are too naive.

Suggested implementation:

- Use scikit-learn `GradientBoostingRegressor`.
- Train three regressors on lag features:
  - median/prediction model: `loss="quantile", alpha=0.5`
  - lower model: `loss="quantile", alpha=lower_quantile`
  - upper model: `loss="quantile", alpha=upper_quantile`
- Build training rows from a univariate series:
  - features: previous `lags` values
  - target: next value

Default config:

```json
{
  "model": "quantile_boosting",
  "window": 120,
  "lags": 12,
  "lower_quantile": 0.05,
  "upper_quantile": 0.95,
  "n_estimators": 100,
  "learning_rate": 0.05,
  "max_depth": 3,
  "random_state": 42
}
```

Output mapping:

- `predicted_value`: median quantile prediction
- `lower_bound`: lower quantile prediction
- `upper_bound`: upper quantile prediction
- `model_version`: `quantile_boosting:v1`
- `model_details`: training points, lags, quantiles, estimator params

Risks:

- Needs enough points. With `lags=12`, practical minimum should be at least 40-60 usable values.
- Retraining three boosting models per series per run can be slow if many monitors/metrics are active.
- Does not understand seasonality unless lags cover the seasonal cycle.

### `random_forest`

Purpose:

- Predict next value using non-linear lag relationships.
- Derive uncertainty from distribution of individual tree predictions.

Suggested implementation:

- Use scikit-learn `RandomForestRegressor`.
- Train on the same lag-feature dataset as `quantile_boosting`.
- Get per-tree predictions for the next feature vector.
- Use quantiles of per-tree predictions as the expected interval.

Default config:

```json
{
  "model": "random_forest",
  "window": 120,
  "lags": 12,
  "n_estimators": 200,
  "max_depth": null,
  "min_samples_leaf": 2,
  "lower_quantile": 0.05,
  "upper_quantile": 0.95,
  "random_state": 42
}
```

Output mapping:

- `predicted_value`: forest prediction
- `lower_bound`: lower quantile of tree predictions
- `upper_bound`: upper quantile of tree predictions
- `model_version`: `random_forest:v1`
- `model_details`: training points, lags, tree count, quantiles

Risks:

- Tree-prediction intervals are heuristic, not calibrated probabilistic intervals.
- Can produce overly narrow intervals when trees are highly correlated.
- More CPU/memory heavy than the current statistical models.

### `isolation_forest`

Purpose:

- Detect unusual observations without directly forecasting the next value.
- Useful for point outliers, sudden jumps, drops, and strange local windows.

Contract issue:

- Current `Forecast` contract is forecast-first and `compare()` only knows bounds.
- `IsolationForest` is detection-first: it needs the current actual value to compute an anomaly score.

Recommended MVP approach:

- Add a new evaluation path that can see both history and actual:
  - `evaluate_next(history, actual, config, min_points, rules)`
- Keep `forecast_next()` for backward compatibility with existing tests and statistical models.
- Let ML models return the same persisted fields, plus a model-specific decision.

Suggested implementation:

- Use scikit-learn `IsolationForest`.
- Train on rolling windows of length `lags + 1`.
- Current sample is the latest `lags` historical values plus `actual`.
- Use `decision_function` or `score_samples` as `deviation_score`.
- Set `is_anomaly` from the fitted detector, not from forecast bounds.
- For UI compatibility, still populate:
  - `predicted_value`: historical median or a simple lag-model prediction
  - `lower_bound` / `upper_bound`: empirical quantiles from recent target values

Default config:

```json
{
  "model": "isolation_forest",
  "window": 120,
  "lags": 12,
  "contamination": 0.03,
  "n_estimators": 100,
  "random_state": 42
}
```

Output mapping:

- `predicted_value`: median of recent values
- `lower_bound`: empirical 5th percentile unless configured otherwise
- `upper_bound`: empirical 95th percentile unless configured otherwise
- `deviation_score`: normalized anomaly score or raw decision score
- `model_version`: `isolation_forest:v1`
- `model_details`: training windows, lags, contamination, score, threshold
- anomaly reason: `isolation_score`

Risks:

- Requires a small runner/model contract change because the model needs `actual`.
- `contamination` is sensitive: too high creates alert fatigue; too low misses real incidents.
- Scores are less intuitive than forecast-bound deviations.

## Recommended Architecture

Introduce a richer internal result while preserving the DB/API shape:

```python
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
```

Then add:

```python
def evaluate_next(history: list[float | None], actual: float | None, config: dict, min_points: int, rules: dict | None = None) -> Evaluation:
    ...
```

Behavior:

- Static rules still run first and remain model-independent.
- Forecast-bound models can reuse `forecast_next()` + `compare()`.
- `isolation_forest` can score the actual observation directly.
- Runner writes the same fields it writes today.

This limits changes to:

- `backend/app/timeseries/models.py`
- `backend/app/services/runner.py`
- tests
- docs/default configs
- optional frontend model config helper

## Dependencies

Add backend dependencies:

```toml
"numpy>=2.0.0",
"scikit-learn>=1.5.0",
```

Operational notes:

- Docker backend image will become larger.
- First import of scikit-learn increases cold-start time.
- For MVP, model state can remain stateless and be retrained per run. Persisted model artifacts are not needed yet.

## Configuration Validation

Current API accepts free-form JSON. For this feature, lightweight validation is recommended in model code:

- unknown model -> fallback to `rolling` or return a clear 400 during monitor save/run
- `window >= min_points`
- `lags >= 1`
- `window > lags + min_points`
- `0 < lower_quantile < upper_quantile < 1`
- `0 < contamination < 0.5`
- `n_estimators` capped for MVP, for example `10..500`

Recommended behavior for MVP:

- Invalid config should fail monitor run with a clear error in `runs.error`.
- Do not silently switch models except for missing `model`, which can keep current default `rolling`.

## UI Impact

Minimum:

- No structural UI change is required because the monitor form already exposes `model_config` JSON.
- README/docs should list the three new model names and example configs.

Better MVP UX:

- Replace or supplement raw JSON for model selection with a simple dropdown:
  - Rolling
  - Robust Z
  - Exponential smoothing
  - Seasonal naive
  - Quantile boosting
  - Random forest
  - Isolation forest
- Keep advanced params in JSON.

Chart impact:

- `quantile_boosting` and `random_forest` use existing predicted/bounds lines.
- `isolation_forest` may show empirical bounds that are not the actual decision boundary. `model_details` should make this explicit.

## Test Plan

Backend unit tests:

- `quantile_boosting` returns non-null prediction/bounds after enough history.
- `random_forest` returns non-null prediction/bounds after enough history.
- `isolation_forest` marks a strong spike as anomaly.
- All ML models return no forecast/evaluation when history is below minimum.
- Static rules still override ML decisions.
- Unknown or invalid model config produces a clear failure.

Regression tests:

- Existing `rolling` behavior remains unchanged.
- Existing `compare()` tests still pass.
- E2E monitor run still creates `SeriesPoint` and `Anomaly` records.

Performance smoke test:

- Run demo scenario with at least 8-10 metric series and `window=120`.
- Measure run duration for each model.
- Keep a rough MVP target: single monitor run under 2-5 seconds locally for demo data.

## Implementation Tasks

1. Add `numpy` and `scikit-learn` to backend dependencies.
2. Add lag-window helpers in `backend/app/timeseries/models.py`.
3. Add `quantile_boosting()` implementation.
4. Add `random_forest()` implementation.
5. Add `isolation_forest()` implementation.
6. Add `Evaluation` and `evaluate_next()` or equivalent actual-aware path.
7. Update `runner._store_points()` to use the evaluation result.
8. Resolve monitor-vs-series config behavior.
9. Add unit tests for all new model types.
10. Update README model config docs and demo examples.
11. Optionally add frontend model selection presets.

## Open Decisions

- Should monitor-level model edits update existing series immediately?
- Should invalid model config fail on monitor save or only at run time?
- Should `isolation_forest` anomalies use severity based on score, contamination, or relative deviation from median?
- What is the initial supported maximum for `window`, `lags`, and `n_estimators`?
- Is scikit-learn acceptable for the MVP Docker image size and startup cost?

## Recommendation

Implement `quantile_boosting` and `random_forest` first because they fit the current forecast/bounds contract cleanly. Add `isolation_forest` in the same feature only if the runner/model boundary is upgraded to an actual-aware evaluation function.

For a compact MVP delivery, keep model state stateless, retrain from recent stored points, and store all explainability metadata in `series_points.model_details`.
