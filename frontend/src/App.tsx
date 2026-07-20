import { useCallback, useEffect, useMemo, useState } from "react";
import { Activity, AlertTriangle, Database, LineChart, Play, Save, ShieldCheck, Trash2 } from "lucide-react";

import { api, deleteJson, postJson, putJson } from "./api/client";
import { emptyConnection, emptyMonitor } from "./appConfig";
import { formatAnomalyDeviation, formatAnomalyRange, formatAnomalyValue, formatTableValue, mergePoints, monitorToForm, scheduleSummary } from "./appUtils";
import { FormInput, JsonEditor, Metric, StatusPill, Table } from "./components";
import { TimeSeriesChart } from "./TimeSeriesChart";
import { formatFullDate, type ChartRange } from "./chartUtils";
import type { Anomaly, Connection, Dashboard, Monitor, Run, Series, SeriesPoint } from "./types/domain";

type Tab = "dashboard" | "connections" | "monitors" | "series" | "anomalies";

export function App() {
  const [tab, setTab] = useState<Tab>("dashboard");
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [connections, setConnections] = useState<Connection[]>([]);
  const [monitors, setMonitors] = useState<Monitor[]>([]);
  const [anomalies, setAnomalies] = useState<Anomaly[]>([]);
  const [selectedAnomalyId, setSelectedAnomalyId] = useState<string | null>(null);
  const [series, setSeries] = useState<Series[]>([]);
  const [points, setPoints] = useState<SeriesPoint[]>([]);
  const [overviewPoints, setOverviewPoints] = useState<SeriesPoint[]>([]);
  const [pointsLoading, setPointsLoading] = useState(false);
  const [pointsError, setPointsError] = useState("");
  const [selectedMonitor, setSelectedMonitor] = useState("");
  const [selectedSeries, setSelectedSeries] = useState("");
  const [editingMonitorId, setEditingMonitorId] = useState("");
  const [connectionForm, setConnectionForm] = useState(emptyConnection);
  const [monitorForm, setMonitorForm] = useState(emptyMonitor);

  const sortedAnomalies = useMemo(
    () => [...anomalies].sort((left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime()),
    [anomalies],
  );
  const selectedSeriesEntity = series.find((row) => row.id === selectedSeries) ?? null;
  const seriesEmptyTitle = !selectedMonitor ? "Выберите мониторинг" : series.length === 0 ? "Рядов пока нет" : "Выберите временной ряд";
  const seriesEmptyText = !selectedMonitor
    ? "Здесь появится график выбранного ряда."
    : series.length === 0
      ? "Запустите мониторинг, чтобы получить первые метрики."
      : "График откроется после выбора ряда.";

  async function refresh() {
    const [dash, conns, mons, anomalyList] = await Promise.all([
      api<Dashboard>("/dashboard"),
      api<Connection[]>("/connections"),
      api<Monitor[]>("/monitors"),
      api<Anomaly[]>("/anomalies"),
    ]);
    setDashboard(dash);
    setConnections(conns);
    setMonitors(mons);
    setAnomalies(anomalyList);
    if (!monitorForm.connection_id && conns[0]) {
      setMonitorForm((form) => ({ ...form, connection_id: conns[0].id }));
    }
  }

  const loadSeriesPoints = useCallback(async (seriesId: string, range?: ChartRange) => {
    if (!seriesId) {
      setPoints([]);
      setOverviewPoints([]);
      return;
    }
    setPointsLoading(true);
    setPointsError("");
    try {
      const query = new URLSearchParams({ limit: "5000" });
      if (range) {
        query.set("from", new Date(range.from).toISOString());
        query.set("to", new Date(range.to).toISOString());
      }
      const [detailPoints, overview] = await Promise.all([
        api<SeriesPoint[]>(`/series/${seriesId}/points?${query.toString()}`),
        api<SeriesPoint[]>(`/series/${seriesId}/points?resolution=overview&limit=2000`),
      ]);
      setOverviewPoints(overview);
      setPoints((previous) => mergePoints(range ? previous : [], detailPoints));
    } catch (error) {
      setPointsError(error instanceof Error ? error.message : "Unknown error");
    } finally {
      setPointsLoading(false);
    }
  }, []);

  async function loadSeries(monitorId: string) {
    setSelectedMonitor(monitorId);
    setSelectedSeries("");
    setSeries([]);
    setPoints([]);
    setOverviewPoints([]);
    setPointsError("");
    if (!monitorId) {
      return;
    }
    const rows = await api<Series[]>(`/series?monitor_id=${encodeURIComponent(monitorId)}`);
    setSeries(rows);
    if (rows[0]) {
      setSelectedSeries(rows[0].id);
      await loadSeriesPoints(rows[0].id);
    }
  }

  useEffect(() => {
    refresh().catch(() => undefined);
  }, []);

  async function saveConnection() {
    await postJson<Connection>("/connections", connectionForm);
    await refresh();
  }

  async function testConnection(id: string) {
    await postJson<{ ok: boolean; error?: string }>(`/connections/${id}/test`, {});
    await refresh();
  }

  async function saveMonitor() {
    if (editingMonitorId) {
      await putJson<Monitor>(`/monitors/${editingMonitorId}`, monitorForm);
    } else {
      await postJson<Monitor>("/monitors", monitorForm);
    }
    await refresh();
  }

  async function deleteMonitor(monitor: Monitor) {
    if (!window.confirm(`Удалить мониторинг "${monitor.name}"?`)) {
      return;
    }
    await deleteJson<void>(`/monitors/${monitor.id}`);
    if (editingMonitorId === monitor.id) {
      startCreateMonitor();
    }
    if (selectedMonitor === monitor.id) {
      setSelectedMonitor("");
      setSelectedSeries("");
      setSeries([]);
      setPoints([]);
      setOverviewPoints([]);
    }
    await refresh();
  }

  function startCreateMonitor() {
    setEditingMonitorId("");
    setMonitorForm({ ...emptyMonitor, connection_id: connections[0]?.id ?? "" });
  }

  function startEditMonitor(monitor: Monitor) {
    setEditingMonitorId(monitor.id);
    setMonitorForm(monitorToForm(monitor));
  }

  async function runMonitor(id: string) {
    await postJson<Run>(`/monitors/${id}/run`, {});
    await refresh();
    await loadSeries(id);
  }

  return (
    <div className="app">
      <aside>
        <div className="brand">
          <ShieldCheck size={24} />
          <strong>DQ Time Series</strong>
        </div>
        <button className={tab === "dashboard" ? "active" : ""} onClick={() => setTab("dashboard")}>
          <Activity size={18} /> Дэшборд
        </button>
        <button className={tab === "connections" ? "active" : ""} onClick={() => setTab("connections")}>
          <Database size={18} /> Подключения
        </button>
        <button className={tab === "monitors" ? "active" : ""} onClick={() => setTab("monitors")}>
          <Play size={18} /> Мониторинги
        </button>
        <button className={tab === "series" ? "active" : ""} onClick={() => setTab("series")}>
          <LineChart size={18} /> Временные ряды
        </button>
        <button className={tab === "anomalies" ? "active" : ""} onClick={() => setTab("anomalies")}>
          <AlertTriangle size={18} /> Аномалии
        </button>
      </aside>

      <main>
        {tab === "dashboard" && dashboard && (
          <section className="dashboardGrid">
            <Metric title="Активные мониторинги" value={dashboard.active_monitors} />
            <Metric title="Запуски за 24 часа" value={dashboard.runs_24h} />
            <Metric title="Ошибки за 24 часа" value={dashboard.failed_runs_24h} />
            <Metric title="Открытые аномалии" value={dashboard.open_anomalies} />
            <div className="panel dashboardRuns">
              <h2>Последние запуски</h2>
              <Table
                rows={dashboard.latest_runs}
                columns={["status", "new_rows", "metrics_count", "created_at"]}
                render={(run, key) => (key === "status" ? <StatusPill value={run.status} /> : formatTableValue(run, key))}
              />
            </div>
            <div className="panel criticalEvents">
              <h2>Критические события</h2>
              <div className="eventList">
                {dashboard.latest_anomalies.map((item) => (
                  <div className="event" key={item.id}>
                    <StatusPill value={item.severity} />
                    <div>
                      <strong>{formatFullDate(item.created_at, "UTC")}</strong>
                      <span>{item.reason}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </section>
        )}

        {tab === "connections" && (
          <section className="connectionsLayout">
            <div className="panel connectionFormPanel">
              <h2>Новое подключение</h2>
              <div className="connectionFormGrid">
                <FormInput className="fieldSpan2" label="Название" value={connectionForm.name} onChange={(name) => setConnectionForm({ ...connectionForm, name })} />
                <FormInput className="fieldSpan2" label="Host" value={connectionForm.host} onChange={(host) => setConnectionForm({ ...connectionForm, host })} />
                <FormInput label="Port" type="number" value={connectionForm.port} onChange={(port) => setConnectionForm({ ...connectionForm, port: Number(port) })} />
                <FormInput label="Database" value={connectionForm.database} onChange={(database) => setConnectionForm({ ...connectionForm, database })} />
                <FormInput className="fieldSpan2" label="Username" value={connectionForm.username} onChange={(username) => setConnectionForm({ ...connectionForm, username })} />
                <FormInput className="fieldSpan2" label="Password" value={connectionForm.password} type="password" onChange={(password) => setConnectionForm({ ...connectionForm, password })} />
                <button onClick={saveConnection}>
                  <Save size={18} /> Сохранить
                </button>
              </div>
            </div>
            <div className="panel">
              <h2>Список</h2>
              {connections.map((connection) => (
                <div className="rowCard" key={connection.id}>
                  <div>
                    <strong>{connection.name}</strong>
                    <span>{connection.username}@{connection.host}:{connection.port}/{connection.database}</span>
                  </div>
                  <StatusPill value={connection.last_check_status} />
                  <button onClick={() => testConnection(connection.id)}>Проверить</button>
                </div>
              ))}
            </div>
          </section>
        )}

        {tab === "monitors" && (
          <section className="monitorPage">
            <div className="monitorMasterGrid">
              <div className="panel monitorSection">
                <h2><Database size={18} /> Источник и расписание</h2>
                <div className="monitorFieldGrid">
                  <FormInput label="Название" value={monitorForm.name} onChange={(name) => setMonitorForm({ ...monitorForm, name })} />
                  <label>
                    Подключение
                    <select value={monitorForm.connection_id} onChange={(event) => setMonitorForm({ ...monitorForm, connection_id: event.target.value })}>
                      <option value="">Выберите</option>
                      {connections.map((connection) => (
                        <option key={connection.id} value={connection.id}>{connection.name}</option>
                      ))}
                    </select>
                  </label>
                  <FormInput label="Схема" value={monitorForm.schema_name} onChange={(schema_name) => setMonitorForm({ ...monitorForm, schema_name })} />
                  <FormInput label="Таблица" value={monitorForm.table_name} onChange={(table_name) => setMonitorForm({ ...monitorForm, table_name })} />
                  <FormInput label="Checkpoint" value={monitorForm.checkpoint_column} onChange={(checkpoint_column) => setMonitorForm({ ...monitorForm, checkpoint_column })} />
                  <label>
                    Тип checkpoint
                    <select value={monitorForm.checkpoint_type} onChange={(event) => setMonitorForm({ ...monitorForm, checkpoint_type: event.target.value })}>
                      <option value="timestamp">Timestamp</option>
                      <option value="date">Date</option>
                      <option value="integer">Integer</option>
                      <option value="bigint">Bigint</option>
                    </select>
                  </label>
                  <label className="checkboxRow monitorSpan2">
                    <input
                      type="checkbox"
                      checked={monitorForm.is_active}
                      onChange={(event) => setMonitorForm({ ...monitorForm, is_active: event.target.checked })}
                    />
                    Запускать по расписанию
                  </label>
                  {monitorForm.is_active && (
                    <FormInput
                      className="monitorSpan2"
                      label="Cron"
                      value={monitorForm.schedule_cron}
                      onChange={(schedule_cron) => setMonitorForm({ ...monitorForm, schedule_cron })}
                    />
                  )}
                  <FormInput label="Timezone" value={monitorForm.timezone} onChange={(timezone) => setMonitorForm({ ...monitorForm, timezone })} />
                  <FormInput
                    label="Timeout, seconds"
                    type="number"
                    value={monitorForm.query_timeout_seconds}
                    onChange={(query_timeout_seconds) => setMonitorForm({ ...monitorForm, query_timeout_seconds: Number(query_timeout_seconds) })}
                  />
                </div>
              </div>

              <div className="panel monitorSection">
                <h2><LineChart size={18} /> Метрики и модель</h2>
                <label className="jsonFieldWide">
                  Метрики
                  <JsonEditor value={monitorForm.selected_metrics} onChange={(selected_metrics) => setMonitorForm({ ...monitorForm, selected_metrics: selected_metrics as Record<string, string[]> })} />
                </label>
                <label className="jsonFieldWide">
                  Модель
                  <JsonEditor value={monitorForm.model_config} onChange={(model_config) => setMonitorForm({ ...monitorForm, model_config: model_config as Record<string, unknown> })} />
                </label>
              </div>

              <div className="panel monitorSection">
                <h2><AlertTriangle size={18} /> Правила и уведомления</h2>
                <label className="jsonFieldWide">
                  Static rules
                  <JsonEditor value={monitorForm.static_rules} onChange={(static_rules) => setMonitorForm({ ...monitorForm, static_rules: static_rules as Record<string, unknown> })} />
                </label>
                <label className="jsonFieldWide">
                  Уведомления
                  <JsonEditor value={monitorForm.notification_config} onChange={(notification_config) => setMonitorForm({ ...monitorForm, notification_config: notification_config as Record<string, unknown> })} />
                </label>
                <div className="formActions monitorInlineActions">
                  {editingMonitorId && <button onClick={startCreateMonitor}>Новый мониторинг</button>}
                  <button onClick={saveMonitor}>
                    <Save size={18} /> {editingMonitorId ? "Сохранить" : "Создать мониторинг"}
                  </button>
                </div>
              </div>
            </div>

            <div className="panel monitorListPanel">
              <h2>Мониторинги</h2>
              {monitors.map((monitor) => (
                <div className="rowCard" key={monitor.id}>
                  <div>
                    <strong>{monitor.name}</strong>
                    <span>{monitor.schema_name}.{monitor.table_name}</span>
                    <span>{scheduleSummary(monitor)}</span>
                  </div>
                  <StatusPill value={monitor.is_active ? "active" : "paused"} />
                  <button onClick={() => startEditMonitor(monitor)}>Править</button>
                  <button onClick={() => runMonitor(monitor.id)}>Запуск</button>
                  <button onClick={() => deleteMonitor(monitor)}>
                    <Trash2 size={16} /> Удалить
                  </button>
                </div>
              ))}
            </div>
          </section>
        )}

        {tab === "series" && (
          <section className="panel seriesPanel">
            <div className="toolbar seriesToolbar">
              <label className="seriesControl">
                <span>Мониторинг</span>
                <select value={selectedMonitor} onChange={(event) => loadSeries(event.target.value)} disabled={monitors.length === 0}>
                  <option value="">Выберите мониторинг</option>
                  {monitors.map((monitor) => (
                    <option key={monitor.id} value={monitor.id}>{monitor.name}</option>
                  ))}
                </select>
              </label>
              <label className="seriesControl">
                <span>Временной ряд</span>
                <select
                  value={selectedSeries}
                  disabled={!selectedMonitor || series.length === 0}
                  onChange={async (event) => {
                    setSelectedSeries(event.target.value);
                    await loadSeriesPoints(event.target.value);
                  }}
                >
                  <option value="">{selectedMonitor ? "Выберите ряд" : "Сначала выберите мониторинг"}</option>
                  {series.map((row) => (
                    <option key={row.id} value={row.id}>{row.display_name}</option>
                  ))}
                </select>
              </label>
            </div>
            {selectedSeriesEntity ? (
              <TimeSeriesChart
                series={selectedSeriesEntity}
                points={points}
                overviewPoints={overviewPoints}
                anomalies={anomalies}
                loading={pointsLoading}
                error={pointsError}
                timeZone={monitors.find((monitor) => monitor.id === selectedMonitor)?.timezone}
                onRangeCommit={(range) => selectedSeries && loadSeriesPoints(selectedSeries, range)}
                onRetry={() => selectedSeries && loadSeriesPoints(selectedSeries)}
                onOpenAnomaly={(anomalyId) => {
                  setSelectedAnomalyId(anomalyId);
                  setTab("anomalies");
                }}
              />
            ) : (
              <div className="seriesEmptyState">
                <LineChart size={28} />
                <strong>{seriesEmptyTitle}</strong>
                <span>{seriesEmptyText}</span>
              </div>
            )}
          </section>
        )}

        {tab === "anomalies" && (
          <section className="panel anomaliesPanel">
            <div className="sectionHeader">
              <h2>Список аномалий</h2>
              <span>{sortedAnomalies.length} событий</span>
            </div>
            {sortedAnomalies.length === 0 ? (
              <div className="emptyState">Аномалий нет</div>
            ) : (
              <div className="anomalyList">
                {sortedAnomalies.map((anomaly) => (
                  <article className={`anomalyItem ${selectedAnomalyId === anomaly.id ? "selected" : ""}`} key={anomaly.id}>
                    <div className="anomalyMain">
                      <div className="anomalyReason">
                        <strong>{anomaly.reason}</strong>
                        <span>{formatFullDate(anomaly.created_at, "UTC")}</span>
                      </div>
                      <div className="anomalyBadges">
                        <StatusPill value={anomaly.severity} />
                      </div>
                    </div>
                    <div className="anomalyValues">
                      <div className="anomalyValue">
                        <span>Факт</span>
                        <strong>{formatAnomalyValue(anomaly.actual_value)}</strong>
                      </div>
                      <div className="anomalyValue">
                        <span>Прогноз</span>
                        <strong>{formatAnomalyValue(anomaly.predicted_value)}</strong>
                      </div>
                      <div className="anomalyValue">
                        <span>Диапазон</span>
                        <strong>{formatAnomalyRange(anomaly)}</strong>
                      </div>
                      <div className="anomalyValue danger">
                        <span>Отклонение</span>
                        <strong>{formatAnomalyDeviation(anomaly)}</strong>
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </section>
        )}
      </main>
    </div>
  );
}
