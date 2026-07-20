import type React from "react";
import { useEffect, useState } from "react";

const STATUS_LABELS: Record<string, string> = {
  ok: "Доступно",
  success: "Успешно",
  active: "Активен",
  paused: "Пауза",
  sent: "Отправлено",
  failed: "Ошибка",
  critical: "Критично",
  warning: "Предупреждение",
  retrying: "Повтор",
  checking: "Проверяется",
  pending: "Ожидает",
  error: "Ошибка",
};

const STATUS_TONES: Record<string, "success" | "danger" | "warning" | "neutral"> = {
  ok: "success",
  success: "success",
  active: "success",
  sent: "success",
  failed: "danger",
  critical: "danger",
  error: "danger",
  warning: "warning",
  retrying: "warning",
  checking: "warning",
  pending: "neutral",
  paused: "neutral",
};


export function StatusPill({ value }: { value: string }) {
  const normalized = value.toLowerCase();
  const tone = STATUS_TONES[normalized] ?? "neutral";
  return <span className={`pill ${tone}`}>{STATUS_LABELS[normalized] ?? value}</span>;
}


export function Metric({ title, value, icon }: { title: string; value: number; icon?: React.ReactNode }) {
  return (
    <div className="metric">
      <div className="metricTitle">
        {icon}
        <span>{title}</span>
      </div>
      <strong>{new Intl.NumberFormat("ru-RU").format(value)}</strong>
    </div>
  );
}


export function FormInput({
  label,
  value,
  onChange,
  type = "text",
  className,
}: {
  label: string;
  value: string | number;
  onChange: (value: string) => void;
  type?: string;
  className?: string;
}) {
  return (
    <label className={className}>
      {label}
      <input type={type} value={value} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}


export function JsonEditor({ value, onChange }: { value: unknown; onChange: (next: unknown) => void }) {
  const [text, setText] = useState(() => JSON.stringify(value, null, 2));

  useEffect(() => {
    setText(JSON.stringify(value, null, 2));
  }, [value]);

  return (
    <textarea
      className="jsonEditor"
      value={text}
      spellCheck={false}
      onChange={(event) => {
        setText(event.target.value);
        try {
          onChange(JSON.parse(event.target.value));
        } catch {
          // The editor keeps invalid JSON visible until the user fixes it.
        }
      }}
    />
  );
}


export function Table<T extends { id: string }>({
  rows,
  columns,
  labels,
  render,
}: {
  rows: T[];
  columns: string[];
  labels?: Record<string, string>;
  render: (row: T, key: string) => React.ReactNode;
}) {
  return (
    <div className="table">
      <div className="tableHeader">
        {columns.map((column) => (
          <span key={column}>{labels?.[column] ?? column}</span>
        ))}
      </div>
      {rows.map((row) => (
        <div className="tableRow" key={row.id}>
          {columns.map((column) => (
            <span key={column}>{render(row, column)}</span>
          ))}
        </div>
      ))}
    </div>
  );
}
