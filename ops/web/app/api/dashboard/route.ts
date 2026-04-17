import { NextResponse } from "next/server";
import { existsSync, readFileSync } from "fs";
import { join } from "path";
import { queryRows, opsSchema } from "../../lib/data-api";
import type { DashboardEvent, DashboardSummary } from "../../lib/types";

export const dynamic = "force-dynamic";

type Period = "all" | "year" | "month" | "week";
type LabelMode = "all" | "include" | "exclude";
type QueryRow = Record<string, string | number | boolean | null>;

type DashboardConfig = {
  initialEquityJpy: number | null;
  initialEquityDate: string | null;
  manualAdjustments: Array<{
    year: number;
    amountJpy: number;
    note?: string;
  }>;
  missing: boolean;
};

export async function GET(request: Request) {
  try {
    const url = new URL(request.url);
    const schema = opsSchema(url.searchParams.get("schema"));
    const period = parsePeriod(url.searchParams.get("period"));
    const at = normalizeAt(period, url.searchParams.get("at"));
    const labelMode = parseLabelMode(url.searchParams.get("labelMode"));
    const selectedLabels = parseLabelsParam(url.searchParams.get("labels"));
    const requestedSetting = parseSettingParam(url.searchParams.get("setting"));
    const bounds = periodBounds(period, at);
    const commonWhere = [localDatePredicate(bounds), labelPredicate(labelMode, selectedLabels)].filter(Boolean).join(" and ");
    const summaryWhere = ["trade_date_local is not null", commonWhere].filter(Boolean).join(" and ");
    const summaryWhereClause = `where ${summaryWhere}`;
    const eventWhereClause = commonWhere ? `where ${commonWhere}` : "";
    const assetWhere = transactionTimePredicate(bounds);
    const assetWhereClause = assetWhere ? `where ${assetWhere}` : "";
    const [summaryRows, eventRows, labelRows, periodRows, settingBucketRows, currentBalanceRows, assetRows, startBalanceRows, firstBalanceRows] = await Promise.all([
      queryRows(`
        select
          setting_id,
          setting_labels::text as setting_labels,
          trade_date_local,
          decision_count,
          entered_count,
          skipped_count,
          conflict_count,
          filter_skip_count,
          closed_entry_count,
          winning_entry_count,
          conflict_rate,
          trade_rate,
          win_rate,
          pnl_pips,
          pnl_jpy,
          expected_trade_rate,
          actual_trade_rate,
          expected_win_rate,
          actual_win_rate
        from ${schema}.daily_setting_summary
        ${summaryWhereClause}
        order by trade_date_local desc, setting_id
        limit 120
      `),
      queryRows(`
        select
          fact_event_id,
          setting_id,
          setting_labels::text as setting_labels,
          slot_id,
          trade_date_local,
          decision,
          reason,
          match_status,
          units,
          pnl_pips,
          pnl_jpy,
          expected_trade_rate,
          actual_trade_rate,
          expected_win_rate,
          actual_win_rate,
          created_at
        from ${schema}.runtime_oanda_event_fact
        ${eventWhereClause}
        order by created_at desc
        limit 200
      `),
      queryRows(`
        select distinct label
        from (
          select jsonb_array_elements_text(setting_labels) as label
          from ${schema}.runtime_oanda_event_fact
          union
          select jsonb_array_elements_text(setting_labels) as label
          from ${schema}.setting_metadata
        ) labels
        where label <> ''
        order by label
      `),
      queryRows(`
        select
          ${periodBucketExpression(period)} as bucket,
          count(*) as decision_count,
          count(*) filter (where decision = 'entered') as entered_count,
          count(*) filter (where decision like 'skipped%') as skipped_count,
          count(*) filter (where decision = 'skipped_concurrency') as conflict_count,
          count(*) filter (where decision = 'skipped_filter' or reason = 'filter_rejected') as filter_skip_count,
          count(*) filter (where pnl_pips is not null) as closed_entry_count,
          count(*) filter (where pnl_pips > 0) as winning_entry_count,
          coalesce(sum(pnl_pips), 0) as pnl_pips,
          coalesce(sum(pnl_jpy), 0) as pnl_jpy
        from ${schema}.runtime_oanda_event_fact
        ${summaryWhereClause}
        group by 1
        order by bucket
      `),
      queryRows(`
        select
          f.setting_id,
          coalesce(sm.setting_labels::text, max(f.setting_labels::text)) as setting_labels,
          sm.expected_trade_rate,
          sm.expected_win_rate,
          sm.expected_annualized_pips,
          sm.expected_cagr,
          ${periodBucketExpression(period, "f")} as bucket,
          count(*) as decision_count,
          count(*) filter (where f.decision = 'entered') as entered_count,
          count(*) filter (where f.decision like 'skipped%') as skipped_count,
          count(*) filter (where f.decision = 'skipped_concurrency') as conflict_count,
          count(*) filter (where f.decision = 'skipped_filter' or f.reason = 'filter_rejected') as filter_skip_count,
          count(*) filter (where f.pnl_pips is not null) as closed_entry_count,
          count(*) filter (where f.pnl_pips > 0) as winning_entry_count,
          count(*) filter (where f.decision = 'skipped_kill_switch') as kill_count,
          max(f.trade_date_local) filter (where f.decision = 'skipped_kill_switch') as last_kill_date,
          coalesce(sum(f.pnl_pips), 0) as pnl_pips,
          coalesce(sum(f.pnl_jpy), 0) as pnl_jpy
        from (
          select *
          from ${schema}.runtime_oanda_event_fact
          ${summaryWhereClause}
        ) f
        left join ${schema}.setting_metadata sm on sm.setting_id = f.setting_id
        group by
          f.setting_id,
          sm.setting_labels,
          sm.expected_trade_rate,
          sm.expected_win_rate,
          sm.expected_annualized_pips,
          sm.expected_cagr,
          bucket
        order by f.setting_id, bucket
      `),
      queryRows(`
        select account_balance, transaction_time
        from ${schema}.oanda_latest_account_balance
        order by transaction_time desc
        limit 1
      `),
      queryRows(`
        select bucket::text as bucket, account_balance as equity_jpy, transaction_time
        from (
          select
            ${assetBucketExpression(period)} as bucket,
            account_balance,
            transaction_time,
            row_number() over (
              partition by ${assetBucketExpression(period)}
              order by transaction_time desc, transaction_id desc
            ) as row_number
          from ${schema}.oanda_transactions_normalized
          ${assetWhereClause}
          ${assetWhereClause ? "and" : "where"} account_balance is not null
        ) ranked
        where row_number = 1
        order by bucket
      `),
      queryRows(`
        select account_balance
        from ${schema}.oanda_transactions_normalized
        where account_balance is not null
          ${bounds.start ? `and transaction_time < '${bounds.start}T00:00:00Z'` : ""}
        order by transaction_time desc, transaction_id desc
        limit 1
      `),
      queryRows(`
        select account_balance
        from ${schema}.oanda_transactions_normalized
        where account_balance is not null
          ${bounds.start ? `and transaction_time >= '${bounds.start}T00:00:00Z'` : ""}
          ${bounds.end ? `and transaction_time < '${bounds.end}T00:00:00Z'` : ""}
        order by transaction_time asc, transaction_id asc
        limit 1
      `)
    ]);
    const config = readDashboardConfig();
    const asset = buildAsset({
      config,
      period,
      bounds,
      currentBalanceRows,
      assetRows,
      startBalanceRows,
      firstBalanceRows
    });
    const periodPerformance = buildPeriodPerformance(periodRows);
    const settingPerformance = buildSettingPerformance(settingBucketRows, period, config);
    const selectedSetting = selectSetting(requestedSetting, settingPerformance);
    const selectedSettingPeriodPerformance = buildPeriodPerformance(
      settingBucketRows.filter((row) => row.setting_id === selectedSetting)
    );

    return NextResponse.json({
      schema,
      period,
      at,
      labelMode,
      selectedLabels,
      labels: labelRows.map((row) => String(row.label)).filter(Boolean),
      generatedAt: new Date().toISOString(),
      asset,
      periodPerformance,
      settingPerformance,
      selectedSetting,
      selectedSettingPeriodPerformance,
      summary: summaryRows.map(withParsedLabels) as unknown as DashboardSummary[],
      events: eventRows.map(withParsedLabels) as unknown as DashboardEvent[]
    });
  } catch (error) {
    if (isDbWakingError(error)) {
      return NextResponse.json(
        {
          status: "waking",
          message: "Database is waking up. Retry shortly."
        },
        { status: 503 }
      );
    }
    return NextResponse.json(
      {
        message: error instanceof Error ? error.message : "Unknown dashboard error"
      },
      { status: 500 }
    );
  }
}

function parsePeriod(value: string | null): Period {
  return value === "all" || value === "year" || value === "month" || value === "week" ? value : "all";
}

function parseLabelMode(value: string | null): LabelMode {
  return value === "include" || value === "exclude" ? value : "all";
}

function parseLabelsParam(value: string | null): string[] {
  if (!value) {
    return [];
  }
  return value
    .split(",")
    .map((label) => label.trim())
    .filter(Boolean);
}

function parseSettingParam(value: string | null): string | null {
  if (!value) {
    return null;
  }
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function normalizeAt(period: Period, value: string | null): string {
  const now = new Date();
  const fallbackYear = String(now.getFullYear());
  const fallbackMonth = `${fallbackYear}-${String(now.getMonth() + 1).padStart(2, "0")}`;
  const fallbackDay = `${fallbackMonth}-${String(now.getDate()).padStart(2, "0")}`;
  if (period === "all") {
    return "all";
  }
  if (period === "year") {
    return value && /^\d{4}$/.test(value) ? value : fallbackYear;
  }
  if (period === "month") {
    return value && /^\d{4}-\d{2}$/.test(value) ? value : fallbackMonth;
  }
  return value && /^\d{4}-\d{2}-\d{2}$/.test(value) ? value : fallbackDay;
}

function periodBounds(period: Period, at: string): { start: string | null; end: string | null } {
  if (period === "all") {
    return { start: null, end: null };
  }
  if (period === "year") {
    return { start: `${at}-01-01`, end: `${Number(at) + 1}-01-01` };
  }
  if (period === "month") {
    const [year, month] = at.split("-").map(Number);
    const next = month === 12 ? `${year + 1}-01` : `${year}-${String(month + 1).padStart(2, "0")}`;
    return { start: `${at}-01`, end: `${next}-01` };
  }
  const selected = new Date(`${at}T00:00:00Z`);
  const start = startOfIsoWeek(selected);
  const end = new Date(start);
  end.setUTCDate(end.getUTCDate() + 7);
  return { start: dateText(start), end: dateText(end) };
}

function localDatePredicate(bounds: { start: string | null; end: string | null }): string {
  const clauses = [];
  if (bounds.start) {
    clauses.push(`trade_date_local >= '${bounds.start}'`);
  }
  if (bounds.end) {
    clauses.push(`trade_date_local < '${bounds.end}'`);
  }
  return clauses.join(" and ");
}

function transactionTimePredicate(bounds: { start: string | null; end: string | null }): string {
  const clauses = [];
  if (bounds.start) {
    clauses.push(`transaction_time >= '${bounds.start}T00:00:00Z'`);
  }
  if (bounds.end) {
    clauses.push(`transaction_time < '${bounds.end}T00:00:00Z'`);
  }
  return clauses.join(" and ");
}

function assetBucketExpression(period: Period): string {
  if (period === "all") {
    return "date_trunc('year', transaction_time)::date";
  }
  if (period === "year") {
    return "date_trunc('month', transaction_time)::date";
  }
  return "date_trunc('day', transaction_time)::date";
}

function periodBucketExpression(period: Period, alias?: string): string {
  const column = alias ? `${alias}.trade_date_local` : "trade_date_local";
  if (period === "all") {
    return `date_trunc('year', ${column}::date)::date::text`;
  }
  if (period === "year") {
    return `date_trunc('month', ${column}::date)::date::text`;
  }
  return column;
}

function labelPredicate(labelMode: LabelMode, labels: string[]): string {
  if (labelMode === "all" || labels.length === 0) {
    return "";
  }
  const values = labels.map((label) => `'${sqlString(label)}'`).join(",");
  const exists = `exists (select 1 from jsonb_array_elements_text(setting_labels) as labels(label) where labels.label in (${values}))`;
  return labelMode === "include" ? exists : `not ${exists}`;
}

function dateText(date: Date): string {
  return date.toISOString().slice(0, 10);
}

function startOfIsoWeek(date: Date): Date {
  const start = new Date(date);
  const day = start.getUTCDay();
  const offset = day === 0 ? -6 : 1 - day;
  start.setUTCDate(start.getUTCDate() + offset);
  return start;
}

function sqlString(value: string): string {
  return value.replaceAll("'", "''");
}

function readDashboardConfig(): DashboardConfig {
  const configPath = process.env.OPS_DASHBOARD_CONFIG_PATH ?? join(process.cwd(), "config", "dashboard.json");
  if (!existsSync(configPath)) {
    return { initialEquityJpy: null, initialEquityDate: null, manualAdjustments: [], missing: true };
  }
  const raw = JSON.parse(readFileSync(configPath, "utf8"));
  const adjustments = Array.isArray(raw.manualAdjustments) ? raw.manualAdjustments : [];
  return {
    initialEquityJpy: numberOrNull(raw.initialEquityJpy),
    initialEquityDate: typeof raw.initialEquityDate === "string" ? raw.initialEquityDate : null,
    manualAdjustments: adjustments
      .map((item) => ({
        year: Number(item.year),
        amountJpy: Number(item.amountJpy),
        note: typeof item.note === "string" ? item.note : undefined
      }))
      .filter((item) => Number.isFinite(item.year) && Number.isFinite(item.amountJpy)),
    missing: false
  };
}

function buildAsset({
  config,
  period,
  bounds,
  currentBalanceRows,
  assetRows,
  startBalanceRows,
  firstBalanceRows
}: {
  config: DashboardConfig;
  period: Period;
  bounds: { start: string | null; end: string | null };
  currentBalanceRows: QueryRow[];
  assetRows: QueryRow[];
  startBalanceRows: QueryRow[];
  firstBalanceRows: QueryRow[];
}) {
  const current = currentBalanceRows[0];
  const currentEquity = numberOrNull(current?.account_balance);
  const startEquity =
    period === "all"
      ? config.initialEquityJpy
      : numberOrNull(startBalanceRows[0]?.account_balance) ?? numberOrNull(firstBalanceRows[0]?.account_balance);
  const rawPnl = currentEquity !== null && startEquity !== null ? currentEquity - startEquity : null;
  const manualAdjustment = manualAdjustmentForPeriod(config, period, bounds);
  const adjustedPnl = rawPnl === null ? null : rawPnl - manualAdjustment;
  return {
    current_equity_jpy: currentEquity,
    current_transaction_time: typeof current?.transaction_time === "string" ? current.transaction_time : null,
    start_equity_jpy: startEquity,
    raw_pnl_jpy: rawPnl,
    manual_adjustment_jpy: manualAdjustment,
    adjusted_pnl_jpy: adjustedPnl,
    adjusted_pnl_pct: adjustedPnl !== null && startEquity ? adjustedPnl / startEquity : null,
    config_missing: config.missing,
    points: assetRows
      .map((row) => ({
        bucket: String(row.bucket),
        equity_jpy: numberOrNull(row.equity_jpy),
        transaction_time: String(row.transaction_time)
      }))
      .filter((row): row is { bucket: string; equity_jpy: number; transaction_time: string } => row.equity_jpy !== null)
  };
}

function buildPeriodPerformance(rows: QueryRow[]) {
  let cumulativePips = 0;
  let cumulativeJpy = 0;
  let peakPips = 0;
  let maxDdPips = 0;
  return rows.map((row) => {
    const decisionCount = numberOrZero(row.decision_count);
    const enteredCount = numberOrZero(row.entered_count);
    const conflictCount = numberOrZero(row.conflict_count);
    const closedEntryCount = numberOrZero(row.closed_entry_count);
    const winningEntryCount = numberOrZero(row.winning_entry_count);
    const pnlPips = numberOrZero(row.pnl_pips);
    const pnlJpy = numberOrZero(row.pnl_jpy);
    cumulativePips += pnlPips;
    cumulativeJpy += pnlJpy;
    peakPips = Math.max(peakPips, cumulativePips);
    maxDdPips = Math.min(maxDdPips, cumulativePips - peakPips);
    return {
      bucket: String(row.bucket),
      decision_count: decisionCount,
      entered_count: enteredCount,
      skipped_count: numberOrZero(row.skipped_count),
      conflict_count: conflictCount,
      filter_skip_count: numberOrZero(row.filter_skip_count),
      closed_entry_count: closedEntryCount,
      winning_entry_count: winningEntryCount,
      losing_entry_count: Math.max(0, closedEntryCount - winningEntryCount),
      pnl_pips: pnlPips,
      cumulative_pnl_pips: cumulativePips,
      pnl_jpy: pnlJpy,
      cumulative_pnl_jpy: cumulativeJpy,
      max_dd_pips: maxDdPips,
      conflict_rate: decisionCount === 0 ? null : conflictCount / decisionCount,
      trade_rate: decisionCount === 0 ? null : enteredCount / decisionCount,
      win_rate: closedEntryCount === 0 ? null : winningEntryCount / closedEntryCount
    };
  });
}

function buildSettingPerformance(rows: QueryRow[], period: Period, config: DashboardConfig) {
  const bySetting = new Map<string, QueryRow[]>();
  for (const row of rows) {
    const settingId = String(row.setting_id ?? "");
    if (!settingId) {
      continue;
    }
    bySetting.set(settingId, [...(bySetting.get(settingId) ?? []), row]);
  }
  return Array.from(bySetting.entries())
    .map(([settingId, settingRows]) => {
      const series = buildPeriodPerformance(settingRows);
      const last = series.at(-1);
      const firstRow = settingRows[0] ?? {};
      const decisionCount = series.reduce((sum, row) => sum + row.decision_count, 0);
      const enteredCount = series.reduce((sum, row) => sum + row.entered_count, 0);
      const conflictCount = series.reduce((sum, row) => sum + row.conflict_count, 0);
      const closedEntryCount = series.reduce((sum, row) => sum + row.closed_entry_count, 0);
      const winningEntryCount = series.reduce((sum, row) => sum + row.winning_entry_count, 0);
      const killCount = settingRows.reduce((sum, row) => sum + numberOrZero(row.kill_count), 0);
      const lastKillDate = latestDate(settingRows.map((row) => row.last_kill_date));
      const cumulativePnlJpy = last?.cumulative_pnl_jpy ?? 0;
      return {
        setting_id: settingId,
        setting_labels: parseLabels(firstRow.setting_labels),
        decision_count: decisionCount,
        entered_count: enteredCount,
        conflict_count: conflictCount,
        closed_entry_count: closedEntryCount,
        winning_entry_count: winningEntryCount,
        pnl_pips: last?.cumulative_pnl_pips ?? 0,
        cumulative_pnl_pips: last?.cumulative_pnl_pips ?? 0,
        pnl_jpy: cumulativePnlJpy,
        cumulative_pnl_jpy: cumulativePnlJpy,
        max_dd_pips: series.reduce((min, row) => Math.min(min, row.max_dd_pips), 0),
        conflict_rate: decisionCount === 0 ? null : conflictCount / decisionCount,
        trade_rate: decisionCount === 0 ? null : enteredCount / decisionCount,
        win_rate: closedEntryCount === 0 ? null : winningEntryCount / closedEntryCount,
        expected_trade_rate: numberOrNull(firstRow.expected_trade_rate),
        expected_win_rate: numberOrNull(firstRow.expected_win_rate),
        expected_annualized_pips: numberOrNull(firstRow.expected_annualized_pips),
        expected_cagr: numberOrNull(firstRow.expected_cagr),
        actual_cagr: period === "all" ? calculateCagr(cumulativePnlJpy, config) : null,
        kill_count: killCount,
        last_kill_date: lastKillDate,
        days_since_last_kill: lastKillDate ? daysSince(lastKillDate) : null
      };
    })
    .sort((a, b) => a.setting_id.localeCompare(b.setting_id));
}

function calculateCagr(cumulativePnlJpy: number, config: DashboardConfig) {
  const initialEquity = config.initialEquityJpy;
  if (!initialEquity || initialEquity <= 0 || !config.initialEquityDate) {
    return null;
  }
  const start = new Date(`${config.initialEquityDate}T00:00:00Z`);
  const now = new Date();
  if (Number.isNaN(start.getTime()) || start >= now) {
    return null;
  }
  const endingEquity = initialEquity + cumulativePnlJpy;
  if (endingEquity <= 0) {
    return null;
  }
  const years = (now.getTime() - start.getTime()) / (365.25 * 86400000);
  if (years <= 0) {
    return null;
  }
  return Math.pow(endingEquity / initialEquity, 1 / years) - 1;
}

function selectSetting(requested: string | null, rows: Array<{ setting_id: string }>) {
  if (requested && rows.some((row) => row.setting_id === requested)) {
    return requested;
  }
  return rows[0]?.setting_id ?? null;
}

function latestDate(values: unknown[]) {
  const dates = values.map((value) => (typeof value === "string" ? value : "")).filter(Boolean).sort();
  return dates.at(-1) ?? null;
}

function daysSince(dateTextValue: string) {
  const then = new Date(`${dateTextValue}T00:00:00Z`);
  const now = new Date();
  if (Number.isNaN(then.getTime())) {
    return null;
  }
  return Math.max(0, Math.floor((now.getTime() - then.getTime()) / 86400000));
}

function manualAdjustmentForPeriod(config: DashboardConfig, period: Period, bounds: { start: string | null; end: string | null }) {
  if (period === "month" || period === "week") {
    return 0;
  }
  const startYear = bounds.start ? Number(bounds.start.slice(0, 4)) : null;
  const endYear = bounds.end ? Number(bounds.end.slice(0, 4)) : null;
  return config.manualAdjustments
    .filter((item) => {
      if (period === "all") {
        return true;
      }
      return startYear !== null && item.year >= startYear && (endYear === null || item.year < endYear);
    })
    .reduce((sum, item) => sum + item.amountJpy, 0);
}

function numberOrNull(value: unknown): number | null {
  const numberValue = Number(value);
  return Number.isFinite(numberValue) ? numberValue : null;
}

function numberOrZero(value: unknown): number {
  return numberOrNull(value) ?? 0;
}

function isDbWakingError(error: unknown) {
  const name = error instanceof Error ? error.name : "";
  const message = error instanceof Error ? error.message : String(error);
  const text = `${name} ${message}`;
  return [
    "DatabaseResumingException",
    "Database is resuming",
    "Communications link failure",
    "connection attempt failed",
    "timeout",
    "timed out"
  ].some((pattern) => text.toLowerCase().includes(pattern.toLowerCase()));
}

function withParsedLabels<T extends { setting_labels?: unknown }>(row: T): T & { setting_labels: string[] } {
  return {
    ...row,
    setting_labels: parseLabels(row.setting_labels)
  };
}

function parseLabels(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.map(String);
  }
  if (typeof value !== "string" || value.trim() === "") {
    return [];
  }
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed.map(String) : [];
  } catch {
    return [];
  }
}
