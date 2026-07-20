import { useEffect, useMemo, useState } from "react";
import { RotateCcw } from "lucide-react";
import { useRef } from "react";
import {
  Area,
  Brush,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  buildChartRows,
  chooseInitialRange,
  filterRowsByRange,
  formatFullDate,
  formatMetricValue,
  formatTimeTick,
  hasForecast,
  rangeFromBrush,
  toMillis,
  xDomain,
  yDomain,
  type ChartRange,
  type ChartRow,
} from "./chartUtils";
import type { Anomaly, Series, SeriesPoint } from "./types/domain";

type Props = {
  series: Series | null;
  points: SeriesPoint[];
  overviewPoints: SeriesPoint[];
  anomalies: Anomaly[];
  loading: boolean;
  error?: string;
  timeZone?: string;
  onRangeCommit: (range: ChartRange) => void;
  onRetry: () => void;
  onOpenAnomaly: (anomalyId: string) => void;
};

export function TimeSeriesChart({
  series,
  points,
  overviewPoints,
  anomalies,
  loading,
  error,
  timeZone,
  onRangeCommit,
  onRetry,
  onOpenAnomaly,
}: Props) {
  const storageKey = series ? `dq.chart.range.${series.id}` : "";
  const [range, setRange] = useState<ChartRange | null>(null);
  const [pendingCommit, setPendingCommit] = useState<ChartRange | null>(null);
  const initializedSeriesId = useRef<string | null>(null);

  const relevantAnomalies = useMemo(
    () => anomalies.filter((anomaly) => !series || anomaly.series_id === series.id),
    [anomalies, series],
  );
  const rows = useMemo(() => buildChartRows(points, relevantAnomalies), [points, relevantAnomalies]);
  const overviewRows = useMemo(() => buildChartRows(overviewPoints, relevantAnomalies), [overviewPoints, relevantAnomalies]);

  useEffect(() => {
    if (!series) {
      initializedSeriesId.current = null;
      setRange(null);
      return;
    }
    if (overviewPoints.length === 0) {
      if (initializedSeriesId.current !== series.id) {
        initializedSeriesId.current = series.id;
        setRange(null);
      }
      return;
    }

    const initialRange = chooseInitialRange(overviewPoints);
    setRange((currentRange) => {
      if (initializedSeriesId.current !== series.id) {
        initializedSeriesId.current = series.id;
        sessionStorage.removeItem(storageKey);
        return initialRange;
      }
      if (!currentRange || currentRange.preset === "all") {
        return initialRange;
      }
      return currentRange;
    });
  }, [overviewPoints, series, storageKey]);

  useEffect(() => {
    if (!pendingCommit) {
      return;
    }
    const timeout = window.setTimeout(() => {
      sessionStorage.setItem(storageKey, JSON.stringify(pendingCommit));
      onRangeCommit(pendingCommit);
      setPendingCommit(null);
    }, 450);
    return () => window.clearTimeout(timeout);
  }, [onRangeCommit, pendingCommit, storageKey]);

  const visibleRows = useMemo(() => filterRowsByRange(rows, range), [rows, range]);
  const visibleForecast = hasForecast(visibleRows);
  const brushIndexes = useMemo(() => indexesForRange(overviewPoints, range), [overviewPoints, range]);
  const domain = useMemo(() => yDomain(visibleRows, series?.metric_name, true, true), [series?.metric_name, visibleRows]);
  const mainXDomain = useMemo(() => xDomain(range, visibleRows), [range, visibleRows]);
  const forecastStart = visibleRows.find((row) => row.actual === null && hasRowForecast(row))?.x;

  function applyRange(nextRange: ChartRange | null, shouldCommit = true) {
    if (!nextRange) {
      return;
    }
    setRange(nextRange);
    if (shouldCommit) {
      setPendingCommit(nextRange);
    }
  }

  if (!series) {
    return <div className="chartState">Выберите ряд для просмотра.</div>;
  }

  if (overviewPoints.length === 0 && !loading) {
    return (
      <div className="chartState">
        <strong>Для выбранного периода нет данных.</strong>
      </div>
    );
  }

  return (
    <div className="timeSeriesChart">
      {error && (
        <div className="chartError">
          <strong>Ошибка загрузки графика</strong>
          <span>{error}</span>
          <button onClick={onRetry}>
            <RotateCcw size={16} /> Повторить
          </button>
        </div>
      )}

      {!error && visibleRows.length === 0 && (
        <div className="chartState">
          <strong>Для выбранного периода нет данных.</strong>
        </div>
      )}

      <div className="chartFrame">
        {loading && <div className="chartLoading">Загрузка...</div>}
        <ResponsiveContainer width="100%" height={390}>
          <ComposedChart data={visibleRows} margin={{ top: 12, right: 18, bottom: 8, left: 6 }}>
            <CartesianGrid stroke="#e2e8f0" vertical={false} />
            <XAxis
              dataKey="x"
              type="number"
              domain={mainXDomain}
              allowDataOverflow
              tickCount={8}
              tickFormatter={(value) => formatTimeTick(Number(value), range, timeZone)}
              minTickGap={28}
              angle={visibleRows.length > 160 ? -30 : 0}
              textAnchor={visibleRows.length > 160 ? "end" : "middle"}
              tickMargin={10}
            />
            <YAxis
              domain={domain}
              tickFormatter={(value) => formatMetricValue(Number(value), series.metric_name) ?? ""}
              width={64}
            />
            <Tooltip
              content={(props) => (
                <ChartTooltip
                  {...props}
                  rows={visibleRows}
                  metricName={series.metric_name}
                  timeZone={timeZone}
                />
              )}
              cursor={{ stroke: "#94a3b8", strokeDasharray: "3 3" }}
              wrapperStyle={{ outline: "none" }}
            />
            <Area
              dataKey="band"
              type="linear"
              stroke="none"
              fill="#bfdbfe"
              fillOpacity={0.35}
              connectNulls={false}
              isAnimationActive={false}
            />
            <Line
              type="linear"
              dataKey="actual"
              stroke="#0f766e"
              strokeWidth={2.2}
              dot={(props) => (
                <ActualDot
                  {...props}
                  showRegular={visibleRows.length <= 50}
                  onOpenAnomaly={onOpenAnomaly}
                />
              )}
              activeDot={{ r: 5 }}
              connectNulls={false}
              isAnimationActive={false}
            />
            {visibleForecast && (
              <Line
                type="linear"
                dataKey="predicted"
                stroke="#7c3aed"
                strokeWidth={2}
                strokeDasharray="6 5"
                dot={false}
                activeDot={{ r: 4 }}
                connectNulls={false}
                isAnimationActive={false}
              />
            )}
            {forecastStart && (
              <ReferenceLine
                x={forecastStart}
                stroke="#7c3aed"
                strokeDasharray="4 4"
              />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <div className="rangeNavigator">
        <ResponsiveContainer width="100%" height={92}>
          <ComposedChart data={overviewRows} margin={{ top: 4, right: 18, bottom: 0, left: 6 }}>
            <XAxis dataKey="x" hide type="number" domain={["dataMin", "dataMax"]} />
            <YAxis hide domain={["dataMin", "dataMax"]} />
            <Line
              type="linear"
              dataKey="actual"
              stroke="#0f766e"
              strokeWidth={1.4}
              dot={false}
              connectNulls={false}
              isAnimationActive={false}
            />
            <Brush
              dataKey="x"
              height={44}
              travellerWidth={10}
              startIndex={brushIndexes.startIndex}
              endIndex={brushIndexes.endIndex}
              tickFormatter={() => ""}
              onChange={({ startIndex, endIndex }) => {
                applyRange(rangeFromBrush(overviewPoints, startIndex, endIndex));
              }}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function ChartTooltip({
  active,
  payload,
  label,
  rows,
  metricName,
  timeZone,
}: {
  active?: boolean;
  payload?: Array<{ payload?: ChartRow }>;
  label?: number | string;
  rows: ChartRow[];
  metricName: string;
  timeZone?: string;
}) {
  if (!active || !payload?.length) {
    return null;
  }
  const row = nearestTooltipRow(rows, label) ?? payload.find((item) => item.payload)?.payload;
  if (!row) {
    return null;
  }

  const fact = formatMetricValue(row.actual, metricName);
  const forecast = formatMetricValue(row.predicted, metricName);
  const range =
    row.lower === null || row.upper === null
      ? null
      : `${formatMetricValue(row.lower, metricName)} - ${formatMetricValue(row.upper, metricName)}`;
  const lines = [
    { label: "Прогноз", value: forecast, tone: "forecast" },
    { label: "Диапазон", value: range, tone: "band" },
  ].filter((line) => line.value !== null);

  return (
    <div className="chartTooltip">
      <div className="tooltipHeader">
        <span>{formatFullDate(row.x, timeZone)}</span>
      </div>
      {fact && (
        <div className="tooltipFact">
          <span>Факт</span>
          <strong>{fact}</strong>
        </div>
      )}
      {lines.map((line) => (
        <div className={`tooltipLine ${line.tone}`} key={line.label}>
          <span>{line.label}</span>
          <b>{line.value}</b>
        </div>
      ))}
    </div>
  );
}

function nearestTooltipRow(rows: ChartRow[], label?: number | string): ChartRow | null {
  const x = typeof label === "number" ? label : Number(label);
  if (!Number.isFinite(x) || rows.length === 0) {
    return null;
  }
  return rows.reduce((nearest, row) => (Math.abs(row.x - x) < Math.abs(nearest.x - x) ? row : nearest), rows[0]);
}

function ActualDot(props: {
  cx?: number;
  cy?: number;
  payload?: ChartRow;
  showRegular: boolean;
  onOpenAnomaly: (anomalyId: string) => void;
}) {
  if (props.cx === undefined || props.cy === undefined) {
    return null;
  }
  if (props.payload?.anomalyId) {
    return (
      <circle
        className="anomalyMarker"
        cx={props.cx}
        cy={props.cy}
        r={5.5}
        fill="#dc2626"
        stroke="#ffffff"
        strokeWidth={1.8}
        onMouseDown={() => props.onOpenAnomaly(props.payload!.anomalyId!)}
      />
    );
  }
  if (!props.showRegular) {
    return null;
  }
  return <circle cx={props.cx} cy={props.cy} r={2.5} fill="#ffffff" stroke="#0f766e" strokeWidth={1.4} />;
}

function hasRowForecast(row: ChartRow): boolean {
  return row.predicted !== null || row.lower !== null || row.upper !== null || row.band !== null;
}

function indexesForRange(points: SeriesPoint[], range: ChartRange | null): { startIndex: number; endIndex: number } {
  if (points.length === 0 || !range) {
    return { startIndex: 0, endIndex: Math.max(0, points.length - 1) };
  }
  const sorted = [...points].sort((left, right) => toMillis(left.timestamp) - toMillis(right.timestamp));
  const startIndex = sorted.findIndex((point) => toMillis(point.timestamp) >= range.from);
  const endReverseIndex = [...sorted].reverse().findIndex((point) => toMillis(point.timestamp) <= range.to);
  return {
    startIndex: Math.max(0, startIndex),
    endIndex: endReverseIndex < 0 ? sorted.length - 1 : sorted.length - 1 - endReverseIndex,
  };
}

