# Миграции

Локальный MVP создает таблицы на старте backend через SQLAlchemy `Base.metadata.create_all`.

`versions/0001_initial.sql` хранит SQL baseline текущей схемы для аудита и будущего перехода на Alembic. В runtime этот файл не выполняется.
