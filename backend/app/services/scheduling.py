from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import croniter


DEFAULT_CRON = "*/5 * * * *"


def normalize_cron(expression: str) -> str:
    return " ".join(expression.strip().split())


def validate_cron_expression(expression: str) -> str:
    cron = normalize_cron(expression)
    if len(cron.split()) != 5:
        raise ValueError("Cron-выражение должно содержать 5 полей: minute hour day month weekday")
    if not croniter.is_valid(cron):
        raise ValueError("Некорректное cron-выражение")
    return cron


def validate_timezone(timezone_name: str) -> str:
    try:
        ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("Некорректная timezone") from exc
    return timezone_name


def as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def next_scheduled_at(expression: str, timezone_name: str, after: datetime) -> datetime:
    cron = validate_cron_expression(expression)
    zone = ZoneInfo(validate_timezone(timezone_name))
    base = as_utc(after).astimezone(zone)
    scheduled = croniter(cron, base).get_next(datetime)
    if scheduled.tzinfo is None:
        scheduled = scheduled.replace(tzinfo=zone)
    return scheduled.astimezone(timezone.utc)
