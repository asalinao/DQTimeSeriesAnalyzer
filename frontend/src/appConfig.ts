export type ConnectionForm = {
  name: string;
  host: string;
  port: number;
  database: string;
  username: string;
  password: string;
  ssl_params: Record<string, unknown>;
};

export type MonitorForm = {
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
};

export const emptyConnection: ConnectionForm = {
  name: "Demo source PostgreSQL",
  host: "source-postgres",
  port: 5432,
  database: "source",
  username: "dq_readonly",
  password: "dq_readonly",
  ssl_params: { sslmode: "prefer" },
};

export const emptyMonitor: MonitorForm = {
  name: "",
  connection_id: "",
  schema_name: "public",
  table_name: "demo_orders",
  schedule_cron: "*/5 * * * *",
  timezone: "UTC",
  checkpoint_column: "created_at",
  checkpoint_type: "timestamp",
  selected_metrics: {
    __table__: ["row_count"],
    amount: ["avg", "max", "null_ratio"],
    customer_id: ["distinct_count"],
    status: ["distinct_count"],
  },
  model_config: { model: "rolling", window: 30, k: 3 },
  static_rules: { row_count: { min_value: 1 } },
  notification_config: {},
  query_timeout_seconds: 60,
  is_active: false,
};
