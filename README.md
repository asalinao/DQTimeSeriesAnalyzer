# DQ Time Series Service MVP

Локальный MVP для мониторинга качества данных в PostgreSQL: подключения, мониторы, расчет агрегатов по новым строкам, временные ряды, прогноз, аномалии, dashboard и webhook-уведомления.

## Запуск

```bash
docker compose up -d
```

- UI: http://localhost:5173
- API/OpenAPI: http://localhost:8000/docs
- Health: http://localhost:8000/api/v1/health
- Ready: http://localhost:8000/api/v1/ready

По умолчанию `ADMIN_TOKEN=change-me`, поэтому API открыт для локального демо. Для закрытого режима задайте свой `ADMIN_TOKEN` и передавайте его в заголовке `X-Admin-Token`.

## Сервисы Docker Compose

- `postgres` - внутренняя БД сервиса.
- `source-postgres` - отдельная demo/source PostgreSQL с таблицей `public.demo_orders`.
- `backend` - FastAPI API.
- `scheduler` - polling scheduler активных мониторов.
- `frontend` - собранный React UI под nginx.
- `demo-generator` - tool-контейнер генерации синтетических заказов.
- `demo-scenario` - tool-контейнер E2E-прогона 30+ вставок и запусков монитора.

## Demo Source PostgreSQL

Параметры подключения из контейнеров:

| Поле | Значение |
| --- | --- |
| host | `source-postgres` |
| port | `5432` |
| database | `source` |
| username | `dq_readonly` |
| password | `dq_readonly` |
| schema/table | `public.demo_orders` |
| checkpoint | `created_at` |

С хост-машины demo/source БД доступна на `localhost:15432`.

## Генерация данных

```bash
docker compose run --rm demo-generator --mode reset --days 45 --seed 42
docker compose run --rm demo-generator --mode normal --hours 1
docker compose run --rm demo-generator --mode amount_shift --hours 2
```

Параметры:

| Параметр | По умолчанию | Значение |
| --- | --- | --- |
| `--mode` | `normal` | `normal`, `row_spike`, `traffic_drop`, `amount_shift`, `discount_bug`, `null_growth`, `low_unique`, `payment_failures`, `reset`. |
| `--hours` | `1` | Сколько часовых бакетов добавить. |
| `--days` | `45` | Сколько дней истории создать при `--mode reset`. |
| `--base-rate` | `42` | Базовая интенсивность заказов в час. |
| `--late-arrivals-ratio` | `0.01` | Доля строк с более старым `created_at`. |
| `--seed` | не задан | Seed для воспроизводимости. |

## Автоматический demo-сценарий

```bash
docker compose run --rm demo-scenario --reset-source --history-days 45 --normal-runs 31 --anomaly-mode amount_shift --anomaly-runs 1 --seed 42
```

Сценарий создает или переиспользует demo-подключение, создает монитор, делает baseline-запуск, затем выполняет минимум 31 цикл `insert -> monitor run` и добавляет аномальный batch.

## Monitor-конфигурация

Минимальный пример:

```json
{
  "name": "Orders quality",
  "connection_id": "<connection uuid>",
  "schema_name": "public",
  "table_name": "demo_orders",
  "schedule_type": "minutes",
  "schedule_value": "5",
  "timezone": "UTC",
  "checkpoint_column": "created_at",
  "checkpoint_type": "timestamp",
  "selected_metrics": {
    "__table__": ["row_count"],
    "amount": ["avg", "max", "null_ratio"],
    "customer_id": ["distinct_count"],
    "status": ["distinct_count"]
  },
  "model_config": {
    "model": "rolling",
    "window": 30,
    "k": 3
  },
  "static_rules": {
    "row_count": {
      "min_value": 1
    }
  },
  "notification_config": {},
  "query_timeout_seconds": 60,
  "is_active": false
}
```

Поля:

| Поле | Значения |
| --- | --- |
| `schedule_type` | `minutes`, `hourly`, `daily`. Для `minutes` минимальный интервал `5`. |
| `schedule_value` | Положительное целое число строкой. |
| `checkpoint_type` | `timestamp`, `date`, `integer`, `bigint`. Сейчас используется как описание типа checkpoint. |
| `selected_metrics.__table__` | `row_count`, `empty_batch`. `row_count` всегда добавляется, если его забыли указать. |
| Метрики колонок | `min`, `max`, `avg`, `sum`, `stddev`, `null_ratio`, `distinct_count`, `unique_ratio`, `zero_ratio`, `negative_ratio`, `empty_ratio`, `avg_length`. |
| `model_config.model` | `rolling`, `robust_z`, `exp_smoothing`, `seasonal_naive`. По умолчанию используется `rolling`. |
| `static_rules` | Ключом может быть имя ряда (`amount.avg`) или имя метрики (`row_count`). Поддержаны `min_value`, `max_value`, `forbid_null`. |
| `notification_config` | `{}` для UI-only или `{"webhook_url": "https://example.com/hook"}`. Локальные и приватные webhook URL блокируются. |
| `is_active` | `true` включает автоматический polling scheduler, ручной запуск работает всегда. |

## Актуальный API

- `POST /api/v1/auth/login`
- `GET /api/v1/health`
- `GET /api/v1/ready`
- `GET|POST /api/v1/connections`
- `GET|PUT|DELETE /api/v1/connections/{id}`
- `POST /api/v1/connections/{id}/test`
- `GET|POST /api/v1/monitors`
- `GET|PUT|DELETE /api/v1/monitors/{id}`
- `POST /api/v1/monitors/{id}/enable`
- `POST /api/v1/monitors/{id}/disable`
- `POST /api/v1/monitors/{id}/run`
- `GET /api/v1/series?monitor_id=<id>`
- `GET /api/v1/series/{id}/points`
- `GET /api/v1/anomalies`
- `GET /api/v1/anomalies/{id}`
- `PUT /api/v1/anomalies/{id}/status`
- `GET /api/v1/dashboard`

## Проверки

Backend:

```bash
cd backend
python -m pytest
python -m ruff check .
```

Frontend:

```bash
cd frontend
npm run build
```

Чистый локальный перезапуск с пересозданием данных:

```bash
docker compose down -v
docker compose up -d --build
docker compose run --rm demo-scenario --reset-source --normal-runs 31 --anomaly-mode amount_shift --anomaly-runs 1 --seed 42
```
