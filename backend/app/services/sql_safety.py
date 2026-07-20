import re
from dataclasses import dataclass
from typing import Any


IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class UnsafeSqlError(ValueError):
    pass


def ensure_identifier(value: str, label: str = "identifier") -> str:
    if not IDENTIFIER_RE.fullmatch(value):
        raise UnsafeSqlError(f"Invalid {label}: {value}")
    return value


def quote_ident(value: str) -> str:
    return f'"{ensure_identifier(value)}"'


def parse_checkpoint(raw: Any) -> str | None:
    return None if raw is None else str(raw)


@dataclass(frozen=True)
class MetricSpec:
    alias: str
    column_name: str
    metric_name: str
    expression: str


TABLE_METRICS = {
    "row_count": "COUNT(*)",
    "empty_batch": "CASE WHEN COUNT(*) = 0 THEN 1 ELSE 0 END",
}


def column_metric_expression(column_name: str, metric_name: str) -> str | None:
    column = quote_ident(column_name)
    expressions = {
        "min": f"MIN({column})",
        "max": f"MAX({column})",
        "avg": f"AVG({column})",
        "sum": f"SUM({column})",
        "stddev": f"STDDEV_POP({column})",
        "null_ratio": f"SUM(CASE WHEN {column} IS NULL THEN 1 ELSE 0 END)::double precision / NULLIF(COUNT(*), 0)",
        "distinct_count": f"COUNT(DISTINCT {column})",
        "unique_ratio": f"COUNT(DISTINCT {column})::double precision / NULLIF(COUNT(*), 0)",
        "zero_ratio": f"SUM(CASE WHEN {column} = 0 THEN 1 ELSE 0 END)::double precision / NULLIF(COUNT(*), 0)",
        "negative_ratio": f"SUM(CASE WHEN {column} < 0 THEN 1 ELSE 0 END)::double precision / NULLIF(COUNT(*), 0)",
        "empty_ratio": f"SUM(CASE WHEN BTRIM({column}::text) = '' THEN 1 ELSE 0 END)::double precision / NULLIF(COUNT(*), 0)",
        "avg_length": f"AVG(LENGTH({column}::text))",
    }
    return expressions.get(metric_name)


def build_metric_specs(selected_metrics: dict[str, list[str]] | None) -> list[MetricSpec]:
    specs: list[MetricSpec] = []
    metrics = selected_metrics or {"__table__": ["row_count"]}
    for column_name, metric_names in metrics.items():
        if column_name != "__table__":
            ensure_identifier(column_name, "column")
        for metric_name in metric_names:
            ensure_identifier(metric_name, "metric")
            expression = TABLE_METRICS.get(metric_name) if column_name == "__table__" else column_metric_expression(column_name, metric_name)
            if expression:
                alias = f"{column_name.replace('__', 'table')}__{metric_name}"
                specs.append(MetricSpec(alias, column_name, metric_name, expression))

    if not any(spec.column_name == "__table__" and spec.metric_name == "row_count" for spec in specs):
        specs.insert(0, MetricSpec("table__row_count", "__table__", "row_count", TABLE_METRICS["row_count"]))
    return specs


def build_aggregate_sql(
    schema_name: str,
    table_name: str,
    checkpoint_column: str,
    selected_metrics: dict[str, list[str]],
    previous_checkpoint: str | None,
) -> tuple[str, list[MetricSpec]]:
    table = f"{quote_ident(schema_name)}.{quote_ident(table_name)}"
    checkpoint = quote_ident(checkpoint_column)
    specs = build_metric_specs(selected_metrics)
    select_sql = ",\n    ".join(f"{spec.expression} AS {quote_ident(spec.alias)}" for spec in specs)
    checkpoint_filter = f"{checkpoint} > %(previous_checkpoint)s AND " if previous_checkpoint is not None else ""
    return (
        f"SELECT\n    {select_sql}\nFROM {table}\nWHERE {checkpoint_filter}{checkpoint} <= %(current_checkpoint)s",
        specs,
    )


def build_checkpoint_sql(schema_name: str, table_name: str, checkpoint_column: str) -> str:
    return f"SELECT MAX({quote_ident(checkpoint_column)}) AS checkpoint FROM {quote_ident(schema_name)}.{quote_ident(table_name)}"
