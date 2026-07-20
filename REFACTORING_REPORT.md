# Refactoring Report

Дата: 2026-07-20

## Актуальное MVP-поведение

Используемые страницы UI:

- Dashboard: метрики состояния, последние запуски, критические события.
- Подключения: создание PostgreSQL-подключения, проверка подключения, список.
- Мониторы: создание, редактирование, ручной запуск, удаление, включение расписания через `is_active`.
- Временные ряды: выбор монитора и ряда, график факта, аномалий, tooltip, навигация по периоду.
- Аномалии: список найденных аномалий.

API, вызываемые frontend:

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

- `scheduler` раз в минуту ищет активные due-мониторы и запускает `execute_monitor`.
- Отдельного worker/queue в текущем MVP нет.

Актуальные модели БД:

- `connections`
- `monitors`
- `runs`
- `series`
- `series_points`
- `anomalies`
- `notifications`

## Что удалено

- Удален дублирующий compose-сервис `worker` и пакет `backend/app/workers`.
- Удален пустой слой `backend/app/repositories`.
- Удалены модели `User`, `AuditLog`, `AnomalyComment`.
- Удалены поля `Run.is_test` и `Series.model_state`.
- Удалены endpoints:
  - `GET /api/v1/runs`
  - `GET /api/v1/runs/{id}`
  - `POST /api/v1/runs/{id}/retry`
  - `GET /api/v1/series/{id}`
  - `PUT /api/v1/series/{id}/model`
  - `POST /api/v1/series/{id}/reset-model`
  - `POST /api/v1/anomalies/{id}/comments`
  - metadata browsing endpoints подключений: schemas/tables/columns.
- Удалены неиспользуемые API-схемы `ErrorEnvelope`, `ColumnInfo`, `SeriesWithPoints`, `AnomalyCommentCreate`, `NotificationRead`.
- Удалено устаревшее ТЗ `data_quality_mvp_tz.md`, потому что оно содержало старые `/runs`, worker/queue и SQL-mode требования.
- Удалены generated-файлы `backend/dq_time_series_backend.egg-info/*`.
- Удалены неиспользуемые CSS-классы старых layout-версий.

## Что переписано

- `backend/app/main.py`: переход с deprecated startup event на lifespan, исправлены нечитаемые сообщения ошибок.
- `backend/app/services/runner.py`: сохранена логика запуска монитора, удален retry-хвост, исправлены сообщения ошибок.
- `backend/app/services/source_postgres.py`: оставлены только test/checkpoint/aggregate функции текущего MVP.
- `backend/app/services/connections.py` и `backend/app/services/monitors.py`: очищены сообщения ошибок и выделена `_anomaly_ids_for_monitor`.
- `frontend/src/main.tsx`: разделен на сценарный entrypoint и вынесенные модули.
- Добавлены:
  - `frontend/src/appConfig.ts`
  - `frontend/src/appUtils.ts`
  - `frontend/src/components.tsx`
  - `demo-source/common/synthetic_orders.py`
- `demo-generator` и `demo-scenario` теперь используют одну общую реализацию синтетических заказов.
- `backend/migrations/versions/0001_initial.sql` заменен на актуальный baseline текущей MVP-схемы.
- README и docs переписаны под текущую архитектуру.

## Устраненные костыли

- Убран старый `mode: auto` из demo-scenario.
- Убрана runtime-env `VITE_API_BASE_URL` у nginx-контейнера; теперь URL явно передается как build arg.
- Убран fake migration-файл без схемы.
- Убраны settings, которые не читались приложением: `APP_ENV`, `APP_SECRET_KEY`, `DEFAULT_QUERY_TIMEOUT_SECONDS`, `MAX_CONCURRENT_RUNS`, `LOG_LEVEL`.

## Зависимости

- Runtime-зависимости frontend оставлены только для приложения: `react`, `react-dom`, `lucide-react`, `recharts`.
- `vite`, `typescript`, `@vitejs/plugin-react`, `@types/*` перенесены в `devDependencies`.
- Backend-зависимости не удалялись: все текущие зависимости используются runtime-кодом или тестами.

## Новая структура

Ключевые каталоги:

- `backend/app/api` - актуальные API routers.
- `backend/app/services` - бизнес-логика подключений, мониторов, запуска и SQL-агрегатов.
- `backend/app/timeseries` - модели прогнозирования.
- `frontend/src` - React UI, chart и клиент API.
- `demo-source/common` - общая генерация синтетических заказов.
- `demo-source/generator` - tool-контейнер генератора.
- `demo-source/scenario` - tool-контейнер E2E-прогона.

## Проверки

Выполнено:

- `python -m pytest` в backend: 7 passed.
- `python -m ruff check .` в backend: passed.
- `npm run build` через `node:20-alpine` в frontend: passed.
- `docker compose down -v`: локальные volumes очищены.
- `docker compose up -d --build`: стек поднялся из чистых БД.
- `docker compose up -d --remove-orphans`: удален старый orphan-контейнер `worker`.
- `docker compose build demo-generator demo-scenario`: tool-образы пересобраны после выноса общего генератора.
- `docker compose run --rm demo-scenario --reset-source --history-days 45 --normal-runs 31 --anomaly-mode amount_shift --anomaly-runs 1 --seed 42`: passed.
- Smoke API/UI:
  - dashboard: `runs_24h=66`, `open_anomalies=4`;
  - frontend отдает `index-BuH_EC4Q.js` и `index-BKsFH01c.css`;
  - последний demo-монитор: `series=9`;
  - выбранный ряд: `points=33`, `forecast_points=3`;
  - `GET /api/v1/anomalies/{id}` возвращает открытую critical-аномалию.

## Оставшиеся компромиссы

- Локальный MVP по-прежнему использует `Base.metadata.create_all`, а SQL baseline хранится как документация схемы, не как runtime migration runner.
- Ручной запуск монитора синхронный; это проще для демо, но не production-подход.
- `npm audit` сообщает 2 уязвимости в dependency tree. `npm audit fix --force` не применялся, потому что может принести breaking upgrades.
- Пустые директории, оставшиеся после удаления файлов, не удалось удалить командой из-за политики среды выполнения.
