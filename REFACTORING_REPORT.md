# Refactoring Report

Дата: 2026-07-20

## Что переписано

Проект переписан как одна актуальная MVP-реализация без альтернативных режимов и временных compatibility-слоев.

- Backend: заново переписаны `main`, API routers, DB bootstrap, модели, Pydantic-схемы, services, forecasting, SQL builder, source PostgreSQL client, webhook notifications и scheduler.
- Frontend: root entrypoint очищен до монтирования React, приложение вынесено в `frontend/src/App.tsx`; текущие вкладки и пользовательские сценарии сохранены.
- Demo tools: заново переписаны общий генератор синтетических заказов, CLI генератора и E2E demo-сценарий.
- Docker Compose и Dockerfile сохранили тот же пользовательский запуск: `docker compose up -d`.

## Актуальное MVP-поведение

Страницы UI:

- Dashboard: агрегаты состояния, последние запуски, критические события.
- Подключения: создание PostgreSQL-подключения, проверка подключения, список.
- Мониторы: создание, редактирование, ручной запуск, удаление, настройка расписания.
- Временные ряды: выбор монитора и ряда, факт, прогноз, expected range, аномалии, tooltip, brush-навигация.
- Аномалии: минималистичный список событий с фактом, прогнозом, диапазоном и отклонением.

API, которые использует frontend:

- `GET /api/v1/dashboard`
- `GET /api/v1/connections`
- `POST /api/v1/connections`
- `POST /api/v1/connections/{id}/test`
- `GET /api/v1/monitors`
- `POST /api/v1/monitors`
- `PUT /api/v1/monitors/{id}`
- `DELETE /api/v1/monitors/{id}`
- `POST /api/v1/monitors/{id}/run`
- `GET /api/v1/series?monitor_id=<id>`
- `GET /api/v1/series/{id}/points`
- `GET /api/v1/anomalies`

Фоновые задачи:

- `scheduler` раз в минуту ищет активные мониторы, у которых наступило расписание, и запускает `execute_monitor`.
- Redis, queue и отдельный worker не используются.

Модели БД текущего MVP:

- `connections`
- `monitors`
- `runs`
- `series`
- `series_points`
- `anomalies`
- `notifications`

## Что удалено или не возвращено

- Пользовательский SQL-режим мониторинга.
- Redis/worker/queue архитектура.
- Старые `/runs` endpoints, retry-run, comments, per-series model edit/reset.
- Модели пользователей, audit log, comments и промежуточные поля, не используемые MVP.
- Временные feature flags и compatibility-код для старых сценариев.
- Случайная монолитность frontend entrypoint.

## Что упрощено

- `execute_monitor` теперь имеет один линейный поток: checkpoint -> aggregate SQL -> time-series points -> anomaly -> notification.
- SQL builder использует явный whitelist метрик и безопасное quoting/валидацию identifiers.
- CRUD connections/monitors вынесен в понятные services без лишних абстракций.
- Forecasting-модели оставлены только как чистые функции.
- Demo-scenario стал прямым E2E flow без дублирующихся helper-веток.

## Зависимости

Удаления зависимостей не потребовались:

- Backend runtime-зависимости используются приложением: FastAPI, SQLAlchemy, psycopg, pydantic-settings, cryptography, httpx.
- Backend dev-зависимости используются проверками: pytest, ruff.
- Frontend runtime-зависимости используются UI: React, lucide-react, Recharts.

## Проверки

Выполнено:

- `..\.venv\Scripts\python.exe -m pytest` в `backend`: 7 passed.
- `..\.venv\Scripts\python.exe -m ruff check .` в `backend`: passed.
- `.venv\Scripts\python.exe -m py_compile demo-source\common\synthetic_orders.py demo-source\generator\generate_demo_data.py demo-source\scenario\run_monitor_scenario.py`: passed.
- `docker run --rm -v "D:\DQ Time Series Service\frontend:/app" -w /app node:20-alpine npm run build`: passed.
- `docker compose up -d --build`: backend, scheduler и frontend собраны и запущены.
- `docker compose build demo-generator demo-scenario`: tool-образы собраны.
- `docker compose run --rm demo-scenario --reset-source --history-days 45 --normal-runs 31 --anomaly-mode amount_shift --anomaly-runs 1 --seed 42`: passed.

Smoke после E2E:

- `GET /api/v1/ready`: `{"status":"ready","database":"ok","scheduler":"inline"}`.
- Frontend отдает `index-DbZDw5aY.js` и `index-oFPF2Vzo.css`.
- Последний demo-монитор: `Auto synthetic orders 20260720131307`.
- Рядов у последнего монитора: `9`.
- Проверенный ряд: `status.distinct_count`, точек `33`, forecast/range-точек `3`.
- Dashboard: `runs_24h=129`, `open_anomalies=12`.

## Оставшиеся компромиссы

- Локальный MVP по-прежнему создает схему через `Base.metadata.create_all`; SQL baseline хранится как документация схемы для будущего Alembic.
- Ручной запуск монитора синхронный, что подходит для локального MVP, но не является production queue-паттерном.
- Внутренние Docker volumes не очищались при финальной проверке, чтобы не удалять текущие данные пользователя; demo-source таблица была сброшена самим demo-сценарием.
