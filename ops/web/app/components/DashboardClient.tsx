"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";
import type { DashboardEvent, DashboardResponse, DashboardSummary } from "../lib/types";

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; data: DashboardResponse };

export default function DashboardClient() {
  const [state, setState] = useState<LoadState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const response = await fetch("/api/dashboard", { cache: "no-store" });
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload.message ?? "Dashboard API failed");
        }
        if (!cancelled) {
          setState({ status: "ready", data: payload });
        }
      } catch (error) {
        if (!cancelled) {
          setState({
            status: "error",
            message: error instanceof Error ? error.message : "Dashboard load failed"
          });
        }
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  if (state.status === "loading") {
    return <Shell>Loading runtime data...</Shell>;
  }

  if (state.status === "error") {
    return (
      <Shell>
        <section className="notice">
          <h2>Connection needs attention</h2>
          <p>{state.message}</p>
        </section>
      </Shell>
    );
  }

  return (
    <Shell schema={state.data.schema} generatedAt={state.data.generatedAt}>
      <DashboardContent data={state.data} />
    </Shell>
  );
}

function Shell({
  children,
  schema,
  generatedAt
}: {
  children: React.ReactNode;
  schema?: string;
  generatedAt?: string;
}) {
  return (
    <main>
      <header className="topbar">
        <div>
          <p className="eyebrow">timer entry ops</p>
          <h1>Runtime Monitor</h1>
        </div>
        <div className="header-meta">
          <span>{schema ?? "loading"}</span>
          <span>{generatedAt ? compactDate(generatedAt) : "waiting"}</span>
        </div>
      </header>
      {children}
    </main>
  );
}

function DashboardContent({ data }: { data: DashboardResponse }) {
  const [selectedLabel, setSelectedLabel] = useState("all");
  const labelOptions = useMemo(() => uniqueLabels(data), [data]);
  const filteredSummary = useMemo(
    () => filterByLabel(data.summary, selectedLabel),
    [data.summary, selectedLabel]
  );
  const filteredEvents = useMemo(
    () => filterByLabel(data.events, selectedLabel),
    [data.events, selectedLabel]
  );
  const metrics = useMemo(() => aggregateMetrics(filteredSummary), [filteredSummary]);
  const chartRows = useMemo(() => chartData(filteredSummary), [filteredSummary]);
  const highConflict = filteredSummary.filter((row) => (row.conflict_rate ?? 0) >= 0.2);
  const driftRows = filteredSummary
    .map((row) => ({
      ...row,
      tradeDrift: diff(row.actual_trade_rate, row.expected_trade_rate),
      winDrift: diff(row.actual_win_rate, row.expected_win_rate)
    }))
    .sort((a, b) => Math.abs(b.winDrift ?? 0) - Math.abs(a.winDrift ?? 0))
    .slice(0, 6);

  return (
    <>
      <section className="metric-grid">
        <Metric label="decisions" value={formatInt(metrics.decisions)} note="daily facts" />
        <Metric label="entered" value={formatInt(metrics.entered)} note="broker attempts" />
        <Metric label="conflict rate" value={formatPct(metrics.conflictRate)} note="concurrency skips" tone={metrics.conflictRate > 0.15 ? "warn" : "ok"} />
        <Metric label="pnl pips" value={formatNumber(metrics.pnlPips)} note="matched rows" tone={metrics.pnlPips < 0 ? "bad" : "ok"} />
      </section>

      <section className="band compact-band">
        <div className="section-heading">
          <h2>Label Filter</h2>
          <p>Filter dashboard rows by runtime setting labels.</p>
        </div>
        <select value={selectedLabel} onChange={(event) => setSelectedLabel(event.target.value)}>
          <option value="all">all labels</option>
          {labelOptions.map((label) => (
            <option key={label} value={label}>
              {label}
            </option>
          ))}
        </select>
      </section>

      <section className="band">
        <div className="section-heading">
          <h2>Daily Shape</h2>
          <p>Entered count, skipped count, and realized pips by setting day.</p>
        </div>
        <div className="chart-grid">
          <div className="chart-panel">
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={chartRows}>
                <CartesianGrid stroke="#dfe5e2" vertical={false} />
                <XAxis dataKey="label" tick={{ fontSize: 12 }} interval={0} minTickGap={12} />
                <YAxis tick={{ fontSize: 12 }} />
                <Tooltip />
                <Bar dataKey="entered" fill="#2e7d5b" radius={[4, 4, 0, 0]} />
                <Bar dataKey="skipped" fill="#c98d2e" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="chart-panel">
            <ResponsiveContainer width="100%" height={280}>
              <LineChart data={chartRows}>
                <CartesianGrid stroke="#dfe5e2" vertical={false} />
                <XAxis dataKey="label" tick={{ fontSize: 12 }} interval={0} minTickGap={12} />
                <YAxis tick={{ fontSize: 12 }} />
                <Tooltip />
                <Line type="monotone" dataKey="pnlPips" stroke="#2b6cb0" strokeWidth={2} dot={{ r: 3 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </section>

      <section className="band split">
        <div>
          <div className="section-heading">
            <h2>Conflict Watch</h2>
            <p>Concurrency and lock-driven skips that can hide real demand.</p>
          </div>
          <SummaryTable rows={highConflict.length ? highConflict : filteredSummary.slice(0, 6)} compact />
        </div>
        <div>
          <div className="section-heading">
            <h2>Expectation Drift</h2>
            <p>Runtime rate against promotion evidence in execution_spec_json.</p>
          </div>
          <DriftTable rows={driftRows} />
        </div>
      </section>

      <section className="band">
        <div className="section-heading">
          <h2>Recent Events</h2>
          <p>Decision-level feed with match status and skip reasons.</p>
        </div>
        <EventTable rows={filteredEvents} />
      </section>
    </>
  );
}

function Metric({
  label,
  value,
  note,
  tone
}: {
  label: string;
  value: string;
  note: string;
  tone?: "ok" | "warn" | "bad";
}) {
  return (
    <article className={`metric ${tone ?? ""}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{note}</small>
    </article>
  );
}

function SummaryTable({ rows, compact = false }: { rows: DashboardSummary[]; compact?: boolean }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>setting</th>
            <th>labels</th>
            <th>date</th>
            <th>entered</th>
            <th>skipped</th>
            <th>conflict</th>
            {!compact && <th>pips</th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={`${row.setting_id}-${row.trade_date_local}`}>
              <td>{row.setting_id}</td>
              <td>{formatLabels(row.setting_labels)}</td>
              <td>{row.trade_date_local}</td>
              <td>{formatInt(row.entered_count)}</td>
              <td>{formatInt(row.skipped_count)}</td>
              <td>{formatPct(row.conflict_rate)}</td>
              {!compact && <td>{formatNumber(row.pnl_pips)}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DriftTable({ rows }: { rows: Array<DashboardSummary & { tradeDrift: number | null; winDrift: number | null }> }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>setting</th>
            <th>labels</th>
            <th>date</th>
            <th>trade</th>
            <th>win</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={`drift-${row.setting_id}-${row.trade_date_local}`}>
              <td>{row.setting_id}</td>
              <td>{formatLabels(row.setting_labels)}</td>
              <td>{row.trade_date_local}</td>
              <td>{formatSignedPct(row.tradeDrift)}</td>
              <td>{formatSignedPct(row.winDrift)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function EventTable({ rows }: { rows: DashboardEvent[] }) {
  return (
    <div className="table-wrap wide">
      <table>
        <thead>
          <tr>
            <th>time</th>
            <th>setting</th>
            <th>labels</th>
            <th>slot</th>
            <th>decision</th>
            <th>reason</th>
            <th>match</th>
            <th>pips</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.fact_event_id}>
              <td>{compactDate(row.created_at)}</td>
              <td>{row.setting_id}</td>
              <td>{formatLabels(row.setting_labels)}</td>
              <td>{row.slot_id ?? "-"}</td>
              <td>{row.decision ?? "-"}</td>
              <td>{row.reason ?? "-"}</td>
              <td>
                <span className={`pill ${row.match_status ?? ""}`}>{row.match_status ?? "-"}</span>
              </td>
              <td>{formatNumber(row.pnl_pips)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function aggregateMetrics(rows: DashboardSummary[]) {
  const decisions = rows.reduce((sum, row) => sum + row.decision_count, 0);
  const entered = rows.reduce((sum, row) => sum + row.entered_count, 0);
  const conflicts = rows.reduce((sum, row) => sum + row.conflict_count, 0);
  const pnlPips = rows.reduce((sum, row) => sum + (row.pnl_pips ?? 0), 0);
  return {
    decisions,
    entered,
    conflictRate: decisions === 0 ? 0 : conflicts / decisions,
    pnlPips
  };
}

function uniqueLabels(data: DashboardResponse) {
  return Array.from(
    new Set(
      [...data.summary, ...data.events]
        .flatMap((row) => row.setting_labels ?? [])
        .filter((label) => label.trim() !== "")
    )
  ).sort();
}

function filterByLabel<T extends { setting_labels: string[] }>(rows: T[], selectedLabel: string) {
  if (selectedLabel === "all") {
    return rows;
  }
  return rows.filter((row) => row.setting_labels.includes(selectedLabel));
}

function formatLabels(labels: string[]) {
  return labels.length ? labels.join(", ") : "-";
}

function chartData(rows: DashboardSummary[]) {
  return rows
    .slice()
    .reverse()
    .slice(-12)
    .map((row) => ({
      label: `${row.trade_date_local.slice(5)} ${shortSetting(row.setting_id)}`,
      entered: row.entered_count,
      skipped: row.skipped_count,
      pnlPips: row.pnl_pips ?? 0
    }));
}

function shortSetting(value: string) {
  return value.replace("_runtime_v1", "").replace("timed_entry_", "");
}

function compactDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("ja-JP", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  }).format(date);
}

function diff(actual: number | null, expected: number | null) {
  return actual === null || expected === null ? null : actual - expected;
}

function formatInt(value: number | null) {
  return value === null ? "-" : new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(value);
}

function formatNumber(value: number | null) {
  return value === null ? "-" : new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 }).format(value);
}

function formatPct(value: number | null) {
  return value === null ? "-" : `${(value * 100).toFixed(1)}%`;
}

function formatSignedPct(value: number | null) {
  if (value === null) {
    return "-";
  }
  const sign = value > 0 ? "+" : "";
  return `${sign}${(value * 100).toFixed(1)}%`;
}
