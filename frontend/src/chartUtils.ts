import type { Anomaly, SeriesPoint } from "./types/domain";

export type PeriodPreset = "all" | "custom";

export type ChartRange = {
  from: number;
  to: number;
  preset: PeriodPreset;
};

export type ChartRow = {
  id: string;
  x: number;
  timestamp: string;
  actual: number | null;
  predicted: number | null;
  lower: number | null;
  upper: number | null;
  band: [number, number] | null;
  anomaly: number | null;
  anomalySeverity?: string;
  anomalyReason?: string;
  absoluteDeviation?: number | null;
  relativeDeviation?: number | null;
  anomalyId?: string;
};

const MS_PER_HOUR = 60 * 60 * 1000;
const MS_PER_DAY = 24 * MS_PER_HOUR;

export function toMillis(value: string): number {
  return new Date(value).getTime();
}

export function sortPoints(points: SeriesPoint[]): SeriesPoint[] {
  return [...points].sort((left, right) => toMillis(left.timestamp) - toMillis(right.timestamp));
}

export function buildChartRows(points: SeriesPoint[], anomalies: Anomaly[] = []): ChartRow[] {
  const anomalyByPoint = new Map(anomalies.map((anomaly) => [anomaly.point_id, anomaly]));
  return sortPoints(points).map((point) => {
    const anomaly = anomalyByPoint.get(point.id);
    const lower = valueOrNull(point.lower_bound);
    const upper = valueOrNull(point.upper_bound);
    const actual = valueOrNull(point.actual_value);
    return {
      id: point.id,
      x: toMillis(point.timestamp),
      timestamp: point.timestamp,
      actual,
      predicted: valueOrNull(point.predicted_value),
      lower,
      upper,
      band: lower === null || upper === null ? null : [lower, upper],
      anomaly: point.is_anomaly && anomaly ? actual : null,
      anomalySeverity: anomaly?.severity,
      anomalyReason: anomaly?.reason,
      absoluteDeviation: anomaly?.absolute_deviation,
      relativeDeviation: anomaly?.relative_deviation,
      anomalyId: anomaly?.id,
    };
  });
}

export function chooseInitialRange(points: SeriesPoint[]): ChartRange | null {
  const sorted = sortPoints(points);
  if (sorted.length === 0) {
    return null;
  }
  return rangeFromIndexes(sorted, 0, sorted.length - 1, "all");
}

export function filterRowsByRange(rows: ChartRow[], range: ChartRange | null): ChartRow[] {
  if (!range) {
    return rows;
  }
  return rows.filter((row) => row.x >= range.from && row.x <= range.to);
}

export function formatTimeTick(value: number, range: ChartRange | null, timeZone?: string): string {
  const duration = range ? range.to - range.from : 0;
  const options: Intl.DateTimeFormatOptions =
    duration <= MS_PER_HOUR
      ? { hour: "2-digit", minute: "2-digit", second: "2-digit" }
      : duration <= MS_PER_DAY
        ? { hour: "2-digit", minute: "2-digit" }
        : duration <= 31 * MS_PER_DAY
          ? { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }
          : { day: "2-digit", month: "2-digit", year: "numeric" };
  return new Intl.DateTimeFormat("ru-RU", { ...options, timeZone }).format(new Date(value));
}

export function formatFullDate(value: number | string, timeZone?: string): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    hourCycle: "h23",
    timeZone,
  }).formatToParts(new Date(value));
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day} ${values.hour}:${values.minute}:${values.second}`;
}

export function formatMetricValue(value: number | null | undefined, metricName = ""): string | null {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return null;
  }
  const isRatio = metricName.includes("ratio") || metricName.includes("rate") || metricName.includes("percent");
  const displayValue = isRatio ? value * 100 : value;
  const suffix = isRatio ? "%" : "";
  const absolute = Math.abs(displayValue);
  if (!isRatio && absolute >= 1_000_000) {
    return `${trimNumber(displayValue / 1_000_000, 2)}M`;
  }
  if (!isRatio && absolute >= 1_000) {
    return `${trimNumber(displayValue / 1_000, 2)}K`;
  }
  const decimals = Number.isInteger(displayValue) ? 0 : absolute < 10 ? 2 : 1;
  return `${trimNumber(displayValue, decimals)}${suffix}`;
}

export function yDomain(rows: ChartRow[], metricName = "", showForecast = true, showBand = true): [number, number] {
  const values = rows.flatMap((row) => {
    const next = [row.actual, row.anomaly];
    if (showForecast) {
      next.push(row.predicted);
    }
    if (showBand) {
      next.push(row.lower, row.upper);
    }
    return next.filter((value): value is number => value !== null && value !== undefined && !Number.isNaN(value));
  });
  if (values.length === 0) {
    return [0, 1];
  }
  const min = Math.min(...values);
  const max = Math.max(...values);
  if (min === max) {
    const pad = Math.max(Math.abs(min) * 0.1, metricName.includes("ratio") ? 0.01 : 1);
    return [min - pad, max + pad];
  }
  const pad = (max - min) * 0.18;
  return [min - pad, max + pad];
}

export function xDomain(range: ChartRange | null, rows: ChartRow[]): [number, number] | ["dataMin", "dataMax"] {
  if (range && range.to > range.from) {
    return [range.from, range.to];
  }
  const values = rows.map((row) => row.x).filter((value) => !Number.isNaN(value));
  if (values.length === 0) {
    return ["dataMin", "dataMax"];
  }
  const min = Math.min(...values);
  const max = Math.max(...values);
  if (min === max) {
    return [min - MS_PER_HOUR / 2, max + MS_PER_HOUR / 2];
  }
  return [min, max];
}

export function hasForecast(rows: ChartRow[]): boolean {
  return rows.some((row) => row.predicted !== null || row.lower !== null || row.upper !== null);
}

export function rangeFromBrush(points: SeriesPoint[], startIndex?: number, endIndex?: number): ChartRange | null {
  const sorted = sortPoints(points);
  if (sorted.length === 0) {
    return null;
  }
  return rangeFromIndexes(
    sorted,
    Math.max(0, startIndex ?? 0),
    Math.min(sorted.length - 1, endIndex ?? sorted.length - 1),
    "custom",
  );
}

function rangeFromIndexes(points: SeriesPoint[], startIndex: number, endIndex: number, preset: PeriodPreset): ChartRange {
  return {
    from: toMillis(points[startIndex].timestamp),
    to: toMillis(points[endIndex].timestamp),
    preset,
  };
}

function valueOrNull(value: number | null | undefined): number | null {
  return value === null || value === undefined || Number.isNaN(value) ? null : value;
}

function trimNumber(value: number, maximumFractionDigits: number): string {
  return new Intl.NumberFormat("ru-RU", {
    maximumFractionDigits,
    minimumFractionDigits: 0,
  }).format(value);
}
