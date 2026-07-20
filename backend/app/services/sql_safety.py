import re
from dataclasses import dataclass
from typing import Any


IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class UnsafeSqlError(ValueError):
    pass


def ensure_identifier(value: str, label: str = "identifier") -> str:
    if not IDENTIFIER_RE.match(value):
        raise UnsafeSqlError(f"Invalid {label}: {value}")
    return value


def quote_ident(value: str) -> str:
    return f'"{ensure_identifier(value)}"'


def parse_checkpoint(raw: Any) -> str | None:
    if raw is None:
        return None
    return str(raw)


@dataclass(frozen=True)
class MetricSpec:
    alias: str
    column_name: str
    metric_name: str
    expression: str


def build_metric_specs(selected_metrics: dict[str, list[str]]) -> list[MetricSpec]:
    specs: list[MetricSpec] = []
    metrics = selected_metrics or {"__table__": ["row_count"]}
    for column_name, metric_names in metrics.items():
        if column_name != "__table__":
            ensure_identifier(column_name, "column")
        for metric_name in metric_names:
            ensure_identifier(metric_name, "metric")
            alias = f"{column_name.replace('__', 'table')}__{metric_name}"
            if column_name == "__table__":
                if metric_name == "row_count":
                    expr = "COUNT(*)"
                elif metric_name == "empty_batch":
                    expr = "CASE WHEN COUNT(*) = 0 THEN 1 ELSE 0 END"
                else:
                    continue
            else:
                col = quote_ident(column_name)
                if metric_name == "min":
                    expr = f"MIN({col})"
                elif metric_name == "max":
                    expr = f"MAX({col})"
                elif metric_name == "avg":
                    expr = f"AVG({col})"
                elif metric_name == "sum":
                    expr = f"SUM({col})"
                elif metric_name == "stddev":
                    expr = f"STDDEV_POP({col})"
                elif metric_name == "null_ratio":
                    expr = f"SUM(CASE WHEN {col} IS NULL THEN 1 ELSE 0 END)::double precision / NULLIF(COUNT(*), 0)"
                elif metric_name == "distinct_count":
                    expr = f"COUNT(DISTINCT {col})"
                elif metric_name == "unique_ratio":
                    expr = f"COUNT(DISTINCT {col})::double precision / NULLIF(COUNT(*), 0)"
                elif metric_name == "zero_ratio":
                    expr = f"SUM(CASE WHEN {col} = 0 THEN 1 ELSE 0 END)::double precision / NULLIF(COUNT(*), 0)"
                elif metric_name == "negative_ratio":
                    expr = f"SUM(CASE WHEN {col} < 0 THEN 1 ELSE 0 END)::double precision / NULLIF(COUNT(*), 0)"
                elif metric_name == "empty_ratio":
                    expr = f"SUM(CASE WHEN BTRIM({col}::text) = '' THEN 1 ELSE 0 END)::double precision / NULLIF(COUNT(*), 0)"
                elif metric_name == "avg_length":
                    expr = f"AVG(LENGTH({col}::text))"
                else:
                    continue
            specs.append(MetricSpec(alias=alias, column_name=column_name, metric_name=metric_name, expression=expr))
    if not any(spec.metric_name == "row_count" and spec.column_name == "__table__" for spec in specs):
        specs.insert(0, MetricSpec(alias="table__row_count", column_name="__table__", metric_name="row_count", expression="COUNT(*)"))
    return specs


def build_aggregate_sql(
    schema_name: str,
    table_name: str,
    checkpoint_column: str,
    selected_metrics: dict[str, list[str]],
    previous_checkpoint: str | None,
) -> tuple[str, list[MetricSpec]]:
    schema = quote_ident(schema_name)
    table = quote_ident(table_name)
    checkpoint = quote_ident(checkpoint_column)
    specs = build_metric_specs(selected_metrics)
    select_sql = ",\n    ".join(f"{spec.expression} AS {quote_ident(spec.alias)}" for spec in specs)
    lower = f"{checkpoint} > %(previous_checkpoint)s AND " if previous_checkpoint is not None else ""
    where_sql = f"{lower}{checkpoint} <= %(current_checkpoint)s"
    return f"SELECT\n    {select_sql}\nFROM {schema}.{table}\nWHERE {where_sql}", specs


def build_checkpoint_sql(schema_name: str, table_name: str, checkpoint_column: str) -> str:
    return f"SELECT MAX({quote_ident(checkpoint_column)}) AS checkpoint FROM {quote_ident(schema_name)}.{quote_ident(table_name)}"
