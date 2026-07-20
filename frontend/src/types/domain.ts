export type Connection = {
  id: string;
  name: string;
  host: string;
  port: number;
  database: string;
  username: string;
  last_check_status: string;
  last_check_error?: string | null;
};

export type Monitor = {
  id: string;
  name: string;
  connection_id: string;
  schema_name: string;
  table_name: string;
  schedule_cron: string;
  timezone: string;
  checkpoint_column: string;
  checkpoint_type: string;
  selected_metrics: Record<string, string[]>;
  model_config: Record<string, unknown>;
  static_rules: Record<string, unknown>;
  notification_config: Record<string, unknown>;
  query_timeout_seconds: number;
  is_active: boolean;
  last_successful_checkpoint?: string | null;
};

export type Run = {
  id: string;
  monitor_id: string;
  status: string;
  new_rows: number;
  metrics_count: number;
  duration_ms?: number | null;
  error?: string | null;
  created_at: string;
};

export type Series = {
  id: string;
  monitor_id: string;
  column_name: string;
  metric_name: string;
  display_name: string;
  model_config: Record<string, unknown>;
};

export type SeriesPoint = {
  id: string;
  timestamp: string;
  actual_value?: number | null;
  predicted_value?: number | null;
  lower_bound?: number | null;
  upper_bound?: number | null;
  is_anomaly: boolean;
};

export type Anomaly = {
  id: string;
  series_id: string;
  run_id: string;
  point_id: string;
  severity: string;
  status: string;
  reason: string;
  actual_value?: number | null;
  predicted_value?: number | null;
  lower_bound?: number | null;
  upper_bound?: number | null;
  absolute_deviation?: number | null;
  relative_deviation?: number | null;
  created_at: string;
};

export type Dashboard = {
  active_monitors: number;
  runs_24h: number;
  failed_runs_24h: number;
  open_anomalies: number;
  critical_anomalies: number;
  connections: Record<string, number>;
  latest_runs: Run[];
  latest_anomalies: Anomaly[];
};
