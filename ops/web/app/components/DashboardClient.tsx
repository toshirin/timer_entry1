"use client";

import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";
import type { DashboardEvent, DashboardResponse } from "../lib/types";

type LoadState =
  | { status: "loading" }
  | { status: "waking"; attempt: number }
  | { status: "error"; message: string }
  | { status: "ready"; data: DashboardResponse };

type Period = DashboardResponse["period"];
type LabelMode = DashboardResponse["labelMode"];

type ControlsState = {
  schema: string;
  period: Period;
  at: string;
  labelMode: LabelMode;
  labels: string[];
  setting: string | null;
};

export default function DashboardClient() {
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [controls, setControls] = useState<ControlsState>(() => defaultControls());
  const [refreshToken, setRefreshToken] = useState(0);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    setControls(initialControls());
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (!hydrated) {
      return;
    }
    let cancelled = false;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    async function load(attempt = 0) {
      try {
        const response = await fetch(`/api/dashboard?${controlParams(controls)}`, { cache: "no-store" });
        const payload = await response.json();
        if (response.status === 503 && payload.status === "waking" && attempt < 8) {
          if (!cancelled) {
            setState({ status: "waking", attempt: attempt + 1 });
            retryTimer = setTimeout(() => load(attempt + 1), 4000);
          }
          return;
        }
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
      if (retryTimer) {
        clearTimeout(retryTimer);
      }
    };
  }, [controls, refreshToken, hydrated]);

  useEffect(() => {
    if (!hydrated) {
      return;
    }
    const query = controlParams(controls);
    window.history.replaceState(null, "", `${window.location.pathname}?${query}`);
  }, [controls, hydrated]);

  const labelOptions = state.status === "ready" ? state.data.labels : [];
  const updateControls = (next: Partial<ControlsState>) => {
    setState({ status: "loading" });
    setControls((current) => normalizeControls({ ...current, ...next }));
  };
  const shiftPeriod = (direction: -1 | 1) => {
    updateControls({ at: shiftedAt(controls.period, controls.at, direction) });
  };
  const refresh = () => {
    setState({ status: "loading" });
    setRefreshToken((value) => value + 1);
  };

  if (state.status === "loading") {
    return (
      <Shell
        controls={controls}
        labelOptions={labelOptions}
        onChange={updateControls}
        onShift={shiftPeriod}
        onRefresh={refresh}
      >
        Loading runtime data...
      </Shell>
    );
  }

  if (state.status === "waking") {
    return (
      <Shell
        controls={controls}
        labelOptions={labelOptions}
        onChange={updateControls}
        onShift={shiftPeriod}
        onRefresh={refresh}
      >
        Database is waking up... retry {state.attempt}/8
      </Shell>
    );
  }

  if (state.status === "error") {
    return (
      <Shell
        controls={controls}
        labelOptions={labelOptions}
        onChange={updateControls}
        onShift={shiftPeriod}
        onRefresh={refresh}
      >
        <section className="notice">
          <h2>Connection needs attention</h2>
          <p>{state.message}</p>
        </section>
      </Shell>
    );
  }

  return (
    <Shell
      schema={state.data.schema}
      generatedAt={state.data.generatedAt}
      controls={controls}
      labelOptions={state.data.labels}
      onChange={updateControls}
      onShift={shiftPeriod}
      onRefresh={refresh}
    >
      <DashboardContent data={state.data} onSelectSetting={(setting) => updateControls({ setting })} />
    </Shell>
  );
}

function Shell({
  children,
  schema,
  generatedAt,
  controls,
  labelOptions,
  onChange,
  onShift,
  onRefresh
}: {
  children: React.ReactNode;
  schema?: string;
  generatedAt?: string;
  controls: ControlsState;
  labelOptions: string[];
  onChange: (next: Partial<ControlsState>) => void;
  onShift: (direction: -1 | 1) => void;
  onRefresh: () => void;
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
        <DashboardControls
          controls={controls}
          labelOptions={labelOptions}
          onChange={onChange}
          onShift={onShift}
          onRefresh={onRefresh}
        />
      </header>
      {children}
    </main>
  );
}

function DashboardContent({ data, onSelectSetting }: { data: DashboardResponse; onSelectSetting: (setting: string) => void }) {
  const filteredEvents = data.events;

  return (
    <>
      <AssetOverview data={data} />

      <PeriodPerformanceSection rows={data.periodPerformance} />

      <SettingPerformanceSection
        period={data.period}
        rows={data.settingPerformance}
        selectedSetting={data.selectedSetting}
        selectedRows={data.selectedSettingPeriodPerformance}
        onSelect={onSelectSetting}
      />

      <UnitLevelSection current={data.unitLevelCurrent} logs={data.unitLevelLogs} />

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

function SettingPerformanceSection({
  period,
  rows,
  selectedSetting,
  selectedRows,
  onSelect
}: {
  period: DashboardResponse["period"];
  rows: DashboardResponse["settingPerformance"];
  selectedSetting: string | null;
  selectedRows: DashboardResponse["selectedSettingPeriodPerformance"];
  onSelect: (setting: string) => void;
}) {
  const showCagr = period === "all";
  return (
    <section className="band">
      <div className="section-heading">
        <h2>Setting PnL</h2>
        <p>Setting totals for the selected period.</p>
      </div>
      <div className="table-wrap setting-table">
        <table>
          <thead>
            <tr>
              <th>select</th>
              <th>setting</th>
              <th>labels</th>
              <th>level</th>
              <th>pips</th>
              <th>cum pips</th>
              <th>pnl jpy</th>
              <th>cum jpy</th>
              {showCagr && <th>cagr</th>}
              <th>maxDD</th>
              <th>conflict</th>
              <th>trade</th>
              <th>win</th>
              <th>tp</th>
              <th>sl</th>
              <th>forced</th>
              <th>kill</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.setting_id}>
                <td>
                  <input
                    type="radio"
                    name="selected-setting"
                    checked={row.setting_id === selectedSetting}
                    onChange={() => onSelect(row.setting_id)}
                  />
                </td>
                <td>{row.setting_id}</td>
                <td>{formatLabels(row.setting_labels)}</td>
                <td>{formatLevel(row.unit_level, row.setting_labels)}</td>
                <td className={pnlTone(row.pnl_pips)}>{formatNumber(row.pnl_pips)}</td>
                <td className={pnlTone(row.cumulative_pnl_pips)}>
                  {formatWithDelta(row.cumulative_pnl_pips, row.expected_annualized_pips, formatNumber)}
                </td>
                <td className={pnlTone(row.pnl_jpy)}>{formatYen(row.pnl_jpy)}</td>
                <td className={pnlTone(row.cumulative_pnl_jpy)}>{formatYen(row.cumulative_pnl_jpy)}</td>
                {showCagr && <td>{formatWithDelta(row.actual_cagr, row.expected_cagr, formatPct)}</td>}
                <td>{formatNumber(row.max_dd_pips)}</td>
                <td>{formatRateWithCount(row.conflict_rate, row.conflict_count, row.decision_count)}</td>
                <td>{formatRateWithCount(row.trade_rate, row.entered_count, row.decision_count, row.expected_trade_rate)}</td>
                <td>{formatRateWithCount(row.win_rate, row.winning_entry_count, row.closed_entry_count, row.expected_win_rate)}</td>
                <td>{formatRateWithCount(row.tp_hit_rate, row.tp_hit_count, row.closed_entry_count)}</td>
                <td>{formatRateWithCount(row.sl_hit_rate, row.sl_hit_count, row.closed_entry_count)}</td>
                <td>{formatRateWithCount(row.forced_exit_rate, row.forced_exit_count, row.closed_entry_count)}</td>
                <td>{formatKill(row.kill_count, row.days_since_last_kill)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="section-heading sub-heading">
        <h2>{selectedSetting ?? "No setting"}</h2>
        <p>Period PnL for the selected setting.</p>
      </div>
      <PeriodPerformanceSection rows={selectedRows} embedded />
    </section>
  );
}

function UnitLevelSection({
  current,
  logs
}: {
  current: DashboardResponse["unitLevelCurrent"];
  logs: DashboardResponse["unitLevelLogs"];
}) {
  return (
    <section className="band">
      <div className="section-heading">
        <h2>Unit Level</h2>
        <p>Current sizing state and monthly level decisions.</p>
      </div>
      <div className="table-wrap setting-table">
        <table>
          <thead>
            <tr>
              <th>setting</th>
              <th>labels</th>
              <th>level</th>
              <th>size</th>
              <th>unit month</th>
              <th>updated</th>
              <th>updated by</th>
              <th>policy</th>
            </tr>
          </thead>
          <tbody>
            {current.map((row) => (
              <tr key={row.setting_id}>
                <td className="clip-cell" title={row.setting_id}>
                  {row.setting_id}
                </td>
                <td className="clip-cell" title={formatLabels(row.setting_labels)}>
                  {formatLabels(row.setting_labels)}
                </td>
                <td>{formatLevel(row.unit_level, row.setting_labels)}</td>
                <td>{formatUnitSize(row.fixed_units, row.size_scale_pct)}</td>
                <td>{row.unit_level_decision_month ?? "-"}</td>
                <td>{row.unit_level_updated_at ? compactDate(row.unit_level_updated_at) : "-"}</td>
                <td className="clip-cell" title={row.unit_level_updated_by ?? "-"}>
                  {row.unit_level_updated_by ?? "-"}
                </td>
                <td className="clip-cell" title={formatPolicy(row.unit_level_policy_name, row.unit_level_policy_version)}>
                  {formatPolicy(row.unit_level_policy_name, row.unit_level_policy_version)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="section-heading sub-heading">
        <h2>Level Decisions</h2>
        <p>Promotion, demotion, keep, and watch decisions.</p>
      </div>
      <div className="table-wrap wide event-table">
        <table>
          <thead>
            <tr>
              <th>month</th>
              <th>setting</th>
              <th>from to</th>
              <th>decision</th>
              <th>reason</th>
              <th>pnl jpy</th>
              <th>threshold</th>
              <th>units</th>
              <th>applied</th>
              <th>created</th>
            </tr>
          </thead>
          <tbody>
            {logs.map((row) => (
              <tr key={row.decision_log_id}>
                <td>{row.decision_month}</td>
                <td className="clip-cell" title={row.setting_id}>
                  {row.setting_id}
                </td>
                <td>{formatLevelMove(row.current_level, row.next_level)}</td>
                <td>
                  <span className={`pill ${unitDecisionTone(row.decision)}`}>{row.decision}</span>
                </td>
                <td className="clip-cell reason-cell" title={row.decision_reason}>
                  {row.decision_reason}
                </td>
                <td className={pnlTone(row.cum_jpy_month)}>{formatYen(row.cum_jpy_month)}</td>
                <td>{formatYen(row.threshold_jpy)}</td>
                <td>{formatUnits(row.current_units)}</td>
                <td>{row.applied ? "yes" : "no"}</td>
                <td>{compactDate(row.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function PeriodPerformanceSection({ rows, embedded = false }: { rows: DashboardResponse["periodPerformance"]; embedded?: boolean }) {
  return (
    <section className={embedded ? "embedded-section" : "band"}>
      <div className="section-heading">
        <h2>Period PnL</h2>
        <p>Bucket totals with cumulative pips, cumulative JPY, and drawdown.</p>
      </div>
      <PeriodPerformanceTable rows={rows} />
      <div className="chart-grid triple-grid">
        <div className="chart-panel">
          <ResponsiveContainer width="100%" height={280}>
            <ComposedChart data={rows}>
              <CartesianGrid stroke="#dfe5e2" vertical={false} />
              <XAxis dataKey="bucket" tick={{ fontSize: 12 }} minTickGap={12} />
              <YAxis yAxisId="pips" tick={{ fontSize: 12 }} />
              <YAxis yAxisId="jpy" orientation="right" tick={{ fontSize: 12 }} />
              <Tooltip formatter={(value, name) => formatTooltipValue(value, String(name))} />
              <Bar yAxisId="jpy" dataKey="pnl_jpy" fill="#c98d2e" radius={[4, 4, 0, 0]} />
              <Line yAxisId="pips" type="monotone" dataKey="pnl_pips" stroke="#2b6cb0" strokeWidth={2} dot={{ r: 3 }} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
        <div className="chart-panel">
          <ResponsiveContainer width="100%" height={280}>
            <ComposedChart data={rows}>
              <CartesianGrid stroke="#dfe5e2" vertical={false} />
              <XAxis dataKey="bucket" tick={{ fontSize: 12 }} minTickGap={12} />
              <YAxis yAxisId="pips" tick={{ fontSize: 12 }} />
              <YAxis yAxisId="jpy" orientation="right" tick={{ fontSize: 12 }} />
              <Tooltip formatter={(value, name) => formatTooltipValue(value, String(name))} />
              <Bar yAxisId="jpy" dataKey="cumulative_pnl_jpy" fill="#2e7d5b" radius={[4, 4, 0, 0]} />
              <Line yAxisId="pips" type="monotone" dataKey="cumulative_pnl_pips" stroke="#2b6cb0" strokeWidth={2} dot={{ r: 3 }} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
        <div className="chart-panel">
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={rows}>
              <CartesianGrid stroke="#dfe5e2" vertical={false} />
              <XAxis dataKey="bucket" tick={{ fontSize: 12 }} minTickGap={12} />
              <YAxis tick={{ fontSize: 12 }} />
              <Tooltip />
              <Bar dataKey="conflict_count" stackId="events" fill="#b84a45" />
              <Bar dataKey="filter_skip_count" stackId="events" fill="#c98d2e" />
              <Bar dataKey="winning_entry_count" stackId="events" fill="#2e7d5b" />
              <Bar dataKey="losing_entry_count" stackId="events" fill="#7a8890" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </section>
  );
}

function PeriodPerformanceTable({ rows }: { rows: DashboardResponse["periodPerformance"] }) {
  return (
    <div className="table-wrap period-table">
      <table>
        <thead>
          <tr>
            <th>period</th>
            <th>pips</th>
            <th>cum pips</th>
            <th>pnl jpy</th>
            <th>cum jpy</th>
            <th>maxDD</th>
            <th>conflict</th>
            <th>trade</th>
            <th>win</th>
            <th>tp</th>
            <th>sl</th>
            <th>forced</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.bucket}>
              <td>{row.bucket}</td>
              <td className={pnlTone(row.pnl_pips)}>{formatNumber(row.pnl_pips)}</td>
              <td className={pnlTone(row.cumulative_pnl_pips)}>{formatNumber(row.cumulative_pnl_pips)}</td>
              <td className={pnlTone(row.pnl_jpy)}>{formatYen(row.pnl_jpy)}</td>
              <td className={pnlTone(row.cumulative_pnl_jpy)}>{formatYen(row.cumulative_pnl_jpy)}</td>
              <td>{formatNumber(row.max_dd_pips)}</td>
              <td>{formatRateWithCount(row.conflict_rate, row.conflict_count, row.decision_count)}</td>
              <td>{formatRateWithCount(row.trade_rate, row.entered_count, row.decision_count)}</td>
              <td>{formatRateWithCount(row.win_rate, row.winning_entry_count, row.closed_entry_count)}</td>
              <td>{formatRateWithCount(row.tp_hit_rate, row.tp_hit_count, row.closed_entry_count)}</td>
              <td>{formatRateWithCount(row.sl_hit_rate, row.sl_hit_count, row.closed_entry_count)}</td>
              <td>{formatRateWithCount(row.forced_exit_rate, row.forced_exit_count, row.closed_entry_count)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AssetOverview({ data }: { data: DashboardResponse }) {
  const asset = data.asset;
  return (
    <section className="band asset-band">
      <div className="section-heading">
        <h2>Asset</h2>
        <p>Oanda account balance by selected period.</p>
      </div>
      <div className="asset-layout">
        <div className="asset-summary">
          <span>Current equity</span>
          <strong>{formatYen(asset.current_equity_jpy)}</strong>
          <small>
            {formatSignedYen(asset.adjusted_pnl_jpy)} ({formatSignedPct(asset.adjusted_pnl_pct)}) from period start
          </small>
          {asset.manual_adjustment_jpy !== 0 && <small>Manual adjustment {formatSignedYen(asset.manual_adjustment_jpy)}</small>}
          {asset.config_missing && <small>Config file not found: config/dashboard.json</small>}
        </div>
        <div className="chart-panel">
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={asset.points}>
              <CartesianGrid stroke="#dfe5e2" vertical={false} />
              <XAxis dataKey="bucket" tick={{ fontSize: 12 }} minTickGap={12} />
              <YAxis tick={{ fontSize: 12 }} domain={["auto", "auto"]} />
              <Tooltip formatter={(value) => formatYen(Number(value))} />
              <Line type="monotone" dataKey="equity_jpy" stroke="#2e7d5b" strokeWidth={2} dot={{ r: 3 }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </section>
  );
}

function DashboardControls({
  controls,
  labelOptions,
  onChange,
  onShift,
  onRefresh
}: {
  controls: ControlsState;
  labelOptions: string[];
  onChange: (next: Partial<ControlsState>) => void;
  onShift: (direction: -1 | 1) => void;
  onRefresh: () => void;
}) {
  return (
    <div className="control-bar">
      <label>
        <span>DB</span>
        <select value={controls.schema} onChange={(event) => onChange({ schema: event.target.value })}>
          <option value="ops_main">ops_main</option>
          <option value="ops_demo">ops_demo</option>
        </select>
      </label>
      <label>
        <span>Period</span>
        <select value={controls.period} onChange={(event) => onChange({ period: event.target.value as Period })}>
          <option value="all">all</option>
          <option value="year">year</option>
          <option value="month">month</option>
          <option value="week">week</option>
        </select>
      </label>
      <div className="period-control">
        <button type="button" onClick={() => onShift(-1)} disabled={controls.period === "all"}>
          Prev
        </button>
        <input
          type={periodInputType(controls.period)}
          value={periodInputValue(controls)}
          disabled={controls.period === "all"}
          onChange={(event) => onChange({ at: event.target.value })}
        />
        <button type="button" onClick={() => onShift(1)} disabled={controls.period === "all"}>
          Next
        </button>
      </div>
      <label>
        <span>Labels</span>
        <select value={controls.labelMode} onChange={(event) => onChange({ labelMode: event.target.value as LabelMode })}>
          <option value="all">all</option>
          <option value="include">include</option>
          <option value="exclude">exclude</option>
        </select>
      </label>
      <select
        multiple
        className="label-select"
        value={controls.labels}
        disabled={controls.labelMode === "all"}
        onChange={(event) =>
          onChange({
            labels: Array.from(event.currentTarget.selectedOptions).map((option) => option.value)
          })
        }
      >
        {labelOptions.map((label) => (
          <option key={label} value={label}>
            {label}
          </option>
        ))}
      </select>
      <button type="button" onClick={onRefresh}>
        Refresh
      </button>
    </div>
  );
}

function EventTable({ rows }: { rows: DashboardEvent[] }) {
  return (
    <div className="table-wrap wide event-table">
      <table className="event-log-table">
        <thead>
          <tr>
            <th>time</th>
            <th>setting</th>
            <th>labels</th>
            <th>slot</th>
            <th>decision</th>
            <th>reason</th>
            <th>exit</th>
            <th>match</th>
            <th>units</th>
            <th>pips</th>
            <th>pnl jpy</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.fact_event_id}>
              <td>{compactDate(row.created_at)}</td>
              <td className="clip-cell" title={row.setting_id}>
                {row.setting_id}
              </td>
              <td className="clip-cell" title={formatLabels(row.setting_labels)}>
                {formatLabels(row.setting_labels)}
              </td>
              <td>{row.slot_id ?? "-"}</td>
              <td>
                <span className={`pill ${decisionTone(row.decision)}`}>{row.decision ?? "-"}</span>
              </td>
              <td className="clip-cell reason-cell" title={row.reason ?? "-"}>
                {row.reason ?? "-"}
              </td>
              <td className="clip-cell reason-cell" title={row.exit_reason ?? "-"}>
                {row.exit_reason ?? "-"}
              </td>
              <td>
                <span className={`pill ${matchTone(row.match_status)}`}>{row.match_status ?? "-"}</span>
              </td>
              <td>{formatUnits(row.units)}</td>
              <td className={pnlTone(row.pnl_pips)}>{formatNumber(row.pnl_pips)}</td>
              <td className={pnlTone(row.pnl_jpy)}>{formatNumber(row.pnl_jpy)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function formatLabels(labels: string[]) {
  return labels.length ? labels.join(", ") : "-";
}

function formatLevel(level: number | null, labels: string[] = []) {
  const base = level === null ? "-" : `L${level}`;
  return labels.includes("watch") && base !== "-" ? `${base} watch` : base;
}

function formatLevelMove(current: number | null, next: number | null) {
  const from = current === null ? "-" : `L${current}`;
  const to = next === null ? "-" : `L${next}`;
  return `${from} -> ${to}`;
}

function formatUnitSize(fixedUnits: number | null, sizeScalePct: number | null) {
  if (fixedUnits !== null) {
    return `${formatUnits(fixedUnits)}u`;
  }
  if (sizeScalePct !== null) {
    return `${formatNumber(sizeScalePct)}%`;
  }
  return "-";
}

function formatPolicy(name: string | null, version: string | null) {
  if (!name && !version) {
    return "-";
  }
  return [name, version].filter(Boolean).join(" ");
}

function decisionTone(decision: string | null) {
  if (decision === "entered" || decision === "exited") {
    return "ok";
  }
  if (decision?.startsWith("skipped")) {
    return decision === "skipped_filter" ? "muted-pill" : "warn";
  }
  if (decision?.includes("failed")) {
    return "bad";
  }
  return "muted-pill";
}

function unitDecisionTone(decision: string | null) {
  if (decision === "promote") {
    return "ok";
  }
  if (decision === "demote" || decision === "force_level0_watch") {
    return "warn";
  }
  return "muted-pill";
}

function matchTone(matchStatus: string | null) {
  if (matchStatus === "matched") {
    return "ok";
  }
  if (matchStatus === "decision_only" || matchStatus === "oanda_only" || matchStatus === "execution_only") {
    return "warn";
  }
  return "muted-pill";
}

function pnlTone(value: number | null) {
  if (value === null || value === 0) {
    return "number-cell";
  }
  return value > 0 ? "number-cell positive" : "number-cell negative";
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

function formatNumber(value: number | null) {
  return value === null
    ? "-"
    : new Intl.NumberFormat("en-US", {
        minimumFractionDigits: 1,
        maximumFractionDigits: 1
      }).format(value);
}

function formatYen(value: number | null) {
  return value === null
    ? "-"
    : `¥${new Intl.NumberFormat("ja-JP", {
        minimumFractionDigits: 1,
        maximumFractionDigits: 1
      }).format(value)}`;
}

function formatUnits(value: number | null) {
  return value === null
    ? "-"
    : new Intl.NumberFormat("en-US", {
        maximumFractionDigits: 0
      }).format(Math.abs(value));
}

function formatSignedYen(value: number | null) {
  if (value === null) {
    return "-";
  }
  const sign = value > 0 ? "+" : "";
  return `${sign}${formatYen(value)}`;
}

function formatTooltipValue(value: unknown, name: string) {
  const numberValue = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(numberValue)) {
    return String(value);
  }
  return name.includes("jpy") ? formatYen(numberValue) : formatNumber(numberValue);
}

function formatWithDelta(value: number | null, expected: number | null, formatter: (value: number | null) => string) {
  const delta = value !== null && expected !== null ? value - expected : null;
  return (
    <span>
      {formatter(value)}
      {delta !== null && <small className="delta"> ({formatSignedValue(delta, formatter)})</small>}
    </span>
  );
}

function formatRateWithCount(value: number | null, numerator: number, denominator: number, expected?: number | null) {
  const delta = value !== null && expected !== undefined && expected !== null ? value - expected : null;
  return (
    <span className="rate-cell">
      <span>
        {formatPct(value)}
        {delta !== null && <small className="delta"> ({formatSignedPct(delta)})</small>}
      </span>
      <small className="rate-count">
        {numerator}/{denominator}
      </small>
    </span>
  );
}

function formatSignedValue(value: number, formatter: (value: number | null) => string) {
  const sign = value > 0 ? "+" : "";
  return `${sign}${formatter(value)}`;
}

function formatKill(killCount: number, daysSinceLastKill: number | null) {
  if (killCount === 0) {
    return "-";
  }
  return daysSinceLastKill === null ? `${killCount}` : `${killCount} / ${daysSinceLastKill}d`;
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

function initialControls(): ControlsState {
  if (typeof window === "undefined") {
    return defaultControls();
  }
  const params = new URLSearchParams(window.location.search);
  return normalizeControls({
    schema: params.get("schema") ?? "ops_demo",
    period: parsePeriod(params.get("period")),
    at: params.get("at") ?? "",
    labelMode: parseLabelMode(params.get("labelMode")),
    labels: parseLabels(params.get("labels")),
    setting: params.get("setting")
  });
}

function defaultControls(): ControlsState {
  return normalizeControls({
    schema: "ops_demo",
    period: "all",
    at: "",
    labelMode: "all",
    labels: [],
    setting: null
  });
}

function normalizeControls(controls: ControlsState): ControlsState {
  const period = parsePeriod(controls.period);
  const labelMode = parseLabelMode(controls.labelMode);
  return {
    schema: controls.schema === "ops_main" ? "ops_main" : "ops_demo",
    period,
    at: normalizeAt(period, controls.at),
    labelMode,
    labels: Array.from(new Set(controls.labels.filter(Boolean))),
    setting: controls.setting?.trim() || null
  };
}

function controlParams(controls: ControlsState) {
  const params = new URLSearchParams();
  params.set("schema", controls.schema);
  params.set("period", controls.period);
  params.set("at", controls.at);
  params.set("labelMode", controls.labelMode);
  if (controls.labels.length) {
    params.set("labels", controls.labels.join(","));
  }
  if (controls.setting) {
    params.set("setting", controls.setting);
  }
  return params.toString();
}

function parsePeriod(value: unknown): Period {
  return value === "year" || value === "month" || value === "week" ? value : "all";
}

function parseLabelMode(value: unknown): LabelMode {
  return value === "include" || value === "exclude" ? value : "all";
}

function parseLabels(value: string | null) {
  return value ? value.split(",").map((label) => label.trim()).filter(Boolean) : [];
}

function normalizeAt(period: Period, value: string) {
  const now = new Date();
  const year = String(now.getFullYear());
  const month = `${year}-${String(now.getMonth() + 1).padStart(2, "0")}`;
  const day = `${month}-${String(now.getDate()).padStart(2, "0")}`;
  if (period === "all") {
    return "all";
  }
  if (period === "year") {
    return /^\d{4}$/.test(value) ? value : year;
  }
  if (period === "month") {
    return /^\d{4}-\d{2}$/.test(value) ? value : month;
  }
  return /^\d{4}-\d{2}-\d{2}$/.test(value) ? value : day;
}

function periodInputType(period: Period) {
  if (period === "year") {
    return "number";
  }
  if (period === "month") {
    return "month";
  }
  return "date";
}

function periodInputValue(controls: ControlsState) {
  return controls.period === "all" ? "" : controls.at;
}

function shiftedAt(period: Period, value: string, direction: -1 | 1) {
  if (period === "all") {
    return "all";
  }
  if (period === "year") {
    return String(Number(value) + direction);
  }
  if (period === "month") {
    const [year, month] = value.split("-").map(Number);
    const next = new Date(Date.UTC(year, month - 1 + direction, 1));
    return `${next.getUTCFullYear()}-${String(next.getUTCMonth() + 1).padStart(2, "0")}`;
  }
  const next = new Date(`${value}T00:00:00Z`);
  next.setUTCDate(next.getUTCDate() + direction * 7);
  return next.toISOString().slice(0, 10);
}
