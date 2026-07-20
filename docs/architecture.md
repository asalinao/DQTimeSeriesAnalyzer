# Архитектура MVP

DQ Time Series Service состоит из FastAPI backend, React frontend, внутренней PostgreSQL, отдельной demo/source PostgreSQL и одного scheduler-процесса.

Основной поток:

1. Пользователь создает PostgreSQL-подключение. Пароль шифруется и не возвращается через API.
2. Пользователь настраивает монитор: источник, checkpoint-колонку, расписание, JSON метрик, JSON модели, static rules и уведомления.
3. Ручной запуск или scheduler вызывает `execute_monitor`.
4. Backend определяет текущий `MAX(checkpoint_column)` и строит агрегирующий SQL для новых строк:

```sql
checkpoint_column > :previous_checkpoint
AND checkpoint_column <= :current_checkpoint
```

5. Сервис сохраняет только агрегаты как точки временных рядов. Сырые данные источника не копируются во внутреннюю БД.
6. После накопления истории модель строит прогноз и диапазон; static rules работают независимо от истории.
7. Аномалии попадают в UI и, если задан `notification_config.webhook_url`, отправляются webhook-уведомлением.

Компромисс MVP: ручной запуск выполняется синхронно в API, а scheduler использует простой polling раз в минуту. Очередь задач, Redis и отдельный worker не используются.
