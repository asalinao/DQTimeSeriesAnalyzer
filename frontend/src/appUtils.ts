import { emptyMonitor, scheduleTypeLabels, type MonitorForm } from "./appConfig";
import { formatFullDate, formatMetricValue } from "./chartUtils";
import type { Anomaly, Monitor, SeriesPoint } from "./types/domain";


export function mergePoints(previous: SeriesPoint[], next: SeriesPoint[]): SeriesPoint[] {
  const points = new Map(previous.map((point) => [point.id, point]));
  for (const point of next) {
    points.set(point.id, point);
  }
  return [...points.values()].sort((left, right) => new Date(left.timestamp).getTime() - new Date(right.timestamp).getTime());
}


export function formatTableValue(row: object, key: string): string {
  const value = (row as Record<string, unknown>)[key];
  if (value === null || value === undefined) {
    return "";
  }
  if (key.endsWith("_at") && typeof value === "string") {
    return formatFullDate(value, "UTC");
  }
  return String(value);
}


export function formatAnomalyValue(value: number | null | undefined): string {
  return formatMetricValue(value) ?? "-";
}


export function formatAnomalyRange(anomaly: Anomaly): string {
  if (anomaly.lower_bound === null || anomaly.lower_bound === undefined || anomaly.upper_bound === null || anomaly.upper_bound === undefined) {
    return "-";
  }
  return `${formatAnomalyValue(anomaly.lower_bound)} - ${formatAnomalyValue(anomaly.upper_bound)}`;
}


export function formatAnomalyDeviation(anomaly: Anomaly): string {
  const parts: string[] = [];
  if (typeof anomaly.relative_deviation === "number") {
    parts.push(`${new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 1 }).format(anomaly.relative_deviation * 100)}%`);
  }
  if (typeof anomaly.absolute_deviation === "number") {
    parts.push(formatAnomalyValue(anomaly.absolute_deviation));
  }
  return parts.length > 0 ? parts.join(" / ") : "-";
}


export function scheduleSummary(monitor: Monitor): string {
  if (!monitor.is_active) {
    return "Расписание выключено";
  }
  return `Запуск каждые ${monitor.schedule_value} ${scheduleTypeLabels[monitor.schedule_type] ?? "минут"}`;
}


export function monitorToForm(monitor: Monitor): MonitorForm {
  return {
    ...emptyMonitor,
    name: monitor.name,
    connection_id: monitor.connection_id,
    schema_name: monitor.schema_name,
    table_name: monitor.table_name,
    schedule_type: monitor.schedule_type,
    schedule_value: monitor.schedule_value,
    timezone: monitor.timezone,
    checkpoint_column: monitor.checkpoint_column,
    checkpoint_type: monitor.checkpoint_type,
    selected_metrics: monitor.selected_metrics,
    model_config: monitor.model_config,
    static_rules: monitor.static_rules,
    notification_config: monitor.notification_config,
    query_timeout_seconds: monitor.query_timeout_seconds,
    is_active: monitor.is_active,
  };
}
