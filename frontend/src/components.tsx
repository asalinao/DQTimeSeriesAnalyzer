import type React from "react";
import { useEffect, useState } from "react";

export function StatusPill({ value }: { value: string }) {
  return <span className={`pill ${value}`}>{value}</span>;
}

export function JsonEditor({ value, onChange }: { value: unknown; onChange: (next: unknown) => void }) {
  const [text, setText] = useState(JSON.stringify(value, null, 2));
  useEffect(() => setText(JSON.stringify(value, null, 2)), [value]);
  return (
    <textarea
      value={text}
      onChange={(event) => {
        setText(event.target.value);
        try {
          onChange(JSON.parse(event.target.value));
        } catch {
          // Keep invalid JSON visible until the user fixes it.
        }
      }}
      spellCheck={false}
    />
  );
}

export function Metric({ title, value }: { title: string; value: number }) {
  return (
    <div className="metric">
      <span>{title}</span>
      <strong>{value}</strong>
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

export function Table<T extends { id: string }>({
  rows,
  columns,
  render,
}: {
  rows: T[];
  columns: string[];
  render: (row: T, key: string) => React.ReactNode;
}) {
  return (
    <div className="table">
      <div className="tableHeader">
        {columns.map((column) => (
          <span key={column}>{column}</span>
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
