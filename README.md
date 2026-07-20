# DQ Time Series Service

MVP-сервис для мониторинга качества данных в PostgreSQL. Приложение подключается к source-БД, считает метрики по новым строкам, строит временные ряды, прогнозирует ожидаемый диапазон и подсвечивает аномалии.

## Возможности

- PostgreSQL-подключения с проверкой доступности.
- Мониторы таблиц по checkpoint-колонке.
- Табличные и колоночные метрики: `row_count`, `empty_batch`, `min`, `max`, `avg`, `sum`, `stddev`, `null_ratio`, `distinct_count`, `unique_ratio`, `zero_ratio`, `negative_ratio`, `empty_ratio`, `avg_length`.
- Модели поиска аномалий: `rolling`, `robust_z`, `exp_smoothing`, `seasonal_naive`, `quantile_boosting`, `random_forest`, `isolation_forest`.
- Dashboard, список аномалий и графики временных рядов.
- Webhook-уведомления для внешних адресов.
- Локальный demo-source PostgreSQL и генератор синтетических данных.

## Быстрый старт

Нужны Docker и Docker Compose.

```bash
docker compose up -d --build
```

После запуска:

- UI: http://localhost:5173
- API docs: http://localhost:8000/docs
- Health: http://localhost:8000/api/v1/health
- Ready: http://localhost:8000/api/v1/ready

По умолчанию проект использует demo-настройки из `.env.example`. Они подходят только для локального запуска. Для реальной установки создайте `.env` со своими значениями и не добавляйте его в git.

## Переменные окружения

Скопируйте пример и замените значения:

```bash
cp .env.example .env
```

Основные переменные:

| Переменная | Назначение |
| --- | --- |
| `ADMIN_USERNAME` | Логин администратора для UI/API. |
| `ADMIN_PASSWORD` | Пароль администратора. |
| `ADMIN_TOKEN` | Токен, который передается в заголовке `X-Admin-Token`. |
| `ENCRYPTION_KEY` | Ключ для шифрования паролей source-подключений. |
| `DATABASE_URL` | DSN внутренней БД сервиса. |
| `MIN_SERIES_POINTS` | Минимум точек ряда перед расчетом прогноза. |
| `CORS_ORIGINS` | Разрешенные origins для frontend. |

Если `ADMIN_TOKEN=change-me`, backend считает запуск локальным demo-режимом и не требует admin-токен. Для любого не demo-окружения обязательно задайте собственные `ADMIN_PASSWORD`, `ADMIN_TOKEN` и `ENCRYPTION_KEY`.

## Demo Source PostgreSQL

Compose поднимает отдельную source-БД с таблицей `public.demo_orders`.

Параметры подключения из контейнеров:

| Поле | Значение |
| --- | --- |
| Host | `source-postgres` |
| Port | `5432` |
| Database | `source` |
| Username | `dq_readonly` |
| Password | `dq_readonly` |
| Checkpoint | `created_at` |

С хост-машины source-БД доступна на `localhost:15432`.

## Генерация demo-данных

Сбросить source-таблицу и создать историю:

```bash
docker compose run --rm demo-generator --mode reset --days 45 --seed 42
```

Добавить новые данные:

```bash
docker compose run --rm demo-generator --mode normal --hours 1
```

Добавить аномальный batch:

```bash
docker compose run --rm demo-generator --mode amount_shift --hours 2
```

Поддержанные режимы: `normal`, `row_spike`, `traffic_drop`, `amount_shift`, `discount_bug`, `null_growth`, `low_unique`, `payment_failures`, `reset`.

## Автоматический demo-сценарий

Команда ниже создает demo-подключение, монитор, baseline, несколько обычных запусков и один аномальный запуск:

```bash
docker compose run --rm demo-scenario --reset-source --history-days 45 --normal-runs 31 --anomaly-mode amount_shift --anomaly-runs 1 --seed 42
```

После выполнения откройте UI и посмотрите Dashboard, Time Series и Anomalies.

## Локальная разработка

Backend:

```bash
cd backend
python -m venv ../.venv
../.venv/Scripts/python -m pip install -e ".[dev]"
../.venv/Scripts/python -m uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm ci
npm run dev
```

Для frontend можно задать API endpoint через `VITE_API_BASE_URL`, например:

```bash
VITE_API_BASE_URL=http://localhost:8000/api/v1 npm run dev
```

## Проверки

Backend:

```bash
cd backend
../.venv/Scripts/python -m pytest
../.venv/Scripts/python -m ruff check .
```

Frontend:

```bash
cd frontend
npm run build
```

## API

Основные endpoints:

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

Полная интерактивная схема доступна в Swagger UI: http://localhost:8000/docs.

## Что не коммитить

В репозиторий не должны попадать:

- `.env` и любые файлы с реальными секретами;
- локальные БД, дампы и Docker volumes;
- `.venv`, `node_modules`, `dist`, кэши pytest/ruff;
- внутренние отчеты и временные заметки.

Перед публикацией можно проверить список файлов:

```bash
git status --short
git ls-files
```
