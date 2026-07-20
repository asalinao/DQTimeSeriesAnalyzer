from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal


ANOMALY_MODES = ("row_spike", "traffic_drop", "amount_shift", "discount_bug", "null_growth", "low_unique", "payment_failures")
GENERATION_MODES = ("normal", *ANOMALY_MODES, "reset")
STATUSES = ("new", "paid", "shipped", "cancelled", "refunded", "failed")


@dataclass(frozen=True)
class OrderRow:
    created_at: datetime
    amount: Decimal | None
    status: str
    customer_id: int


def generate_rows(
    start_at: datetime,
    hours: int,
    base_rate: float,
    mode: str,
    late_arrivals_ratio: float = 0.0,
) -> list[OrderRow]:
    rows: list[OrderRow] = []
    for hour_offset in range(hours):
        bucket = start_at + timedelta(hours=hour_offset)
        for _ in range(expected_orders_per_hour(bucket, base_rate, mode)):
            created_at = bucket + timedelta(minutes=random.randint(0, 59), seconds=random.randint(0, 59))
            if random.random() < late_arrivals_ratio:
                created_at -= timedelta(hours=random.randint(1, 18), minutes=random.randint(0, 59))
            status = choose_status(mode)
            rows.append(
                OrderRow(
                    created_at=created_at,
                    amount=choose_amount(created_at, status, mode),
                    status=status,
                    customer_id=choose_customer(created_at, mode),
                )
            )
    rows.sort(key=lambda row: row.created_at)
    return rows


def history_start(days: int) -> datetime:
    return datetime.now(UTC).replace(minute=0, second=0, microsecond=0) - timedelta(days=days)


def expected_orders_per_hour(ts: datetime, base_rate: float, mode: str) -> int:
    hour = ts.hour
    weekday = ts.weekday()
    business_peak = 0.65 * _normal_pdf_like(hour, 13, 3.3)
    evening_peak = 0.45 * _normal_pdf_like(hour, 20, 2.2)
    night_factor = 0.35 if 0 <= hour <= 5 else 1.0
    weekend_factor = 0.72 if weekday >= 5 else 1.0
    monday_factor = 1.12 if weekday == 0 else 1.0
    rate = base_rate * (0.55 + business_peak + evening_peak) * night_factor * weekend_factor * monday_factor

    if mode == "row_spike":
        rate *= 4.8
    elif mode == "traffic_drop":
        rate *= 0.18

    return max(0, int(random.gauss(rate, max(1.0, rate * 0.18))))


def choose_customer(ts: datetime, mode: str) -> int:
    if mode == "low_unique":
        return random.randint(1, 8)
    active_pool = 900 + int(180 * math.sin(ts.timetuple().tm_yday / 365 * 2 * math.pi))
    if random.random() < 0.18:
        return random.randint(1, 80)
    return random.randint(1, max(100, active_pool))


def choose_status(mode: str) -> str:
    if mode == "payment_failures":
        weights = (0.10, 0.42, 0.08, 0.08, 0.02, 0.30)
    else:
        weights = (0.12, 0.62, 0.16, 0.05, 0.03, 0.02)
    return random.choices(STATUSES, weights=weights, k=1)[0]


def choose_amount(ts: datetime, status: str, mode: str) -> Decimal | None:
    if mode == "null_growth" and random.random() < 0.35:
        return None

    seasonal = 1.0 + 0.08 * math.sin(ts.timetuple().tm_yday / 365 * 2 * math.pi)
    weekend = 0.92 if ts.weekday() >= 5 else 1.0
    status_factor = 0.65 if status in {"cancelled", "refunded", "failed"} else 1.0
    median_amount = 105.0 * seasonal * weekend * status_factor

    if mode == "amount_shift":
        median_amount *= 1.9
    elif mode == "discount_bug":
        median_amount *= 0.28

    amount = random.lognormvariate(math.log(median_amount), 0.42)
    if random.random() < 0.025:
        amount *= random.uniform(2.5, 6.0)
    return Decimal(str(round(_clamp(amount, 1.0, 5000.0), 2)))


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _normal_pdf_like(hour: int, center: int, width: float) -> float:
    return math.exp(-((hour - center) ** 2) / (2 * width**2))
