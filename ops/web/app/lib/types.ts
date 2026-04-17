export type DashboardSummary = {
  setting_id: string;
  setting_labels: string[];
  trade_date_local: string | null;
  decision_count: number;
  entered_count: number;
  skipped_count: number;
  conflict_count: number;
  filter_skip_count: number;
  closed_entry_count: number;
  winning_entry_count: number;
  conflict_rate: number | null;
  trade_rate: number | null;
  win_rate: number | null;
  pnl_pips: number | null;
  pnl_jpy: number | null;
  expected_trade_rate: number | null;
  actual_trade_rate: number | null;
  expected_win_rate: number | null;
  actual_win_rate: number | null;
};

export type DashboardEvent = {
  fact_event_id: string;
  setting_id: string;
  setting_labels: string[];
  slot_id: string | null;
  trade_date_local: string | null;
  decision: string | null;
  reason: string | null;
  match_status: string | null;
  units: number | null;
  pnl_pips: number | null;
  pnl_jpy: number | null;
  expected_trade_rate: number | null;
  actual_trade_rate: number | null;
  expected_win_rate: number | null;
  actual_win_rate: number | null;
  created_at: string;
};

export type DashboardAssetPoint = {
  bucket: string;
  equity_jpy: number;
  transaction_time: string;
};

export type DashboardAsset = {
  current_equity_jpy: number | null;
  current_transaction_time: string | null;
  start_equity_jpy: number | null;
  raw_pnl_jpy: number | null;
  manual_adjustment_jpy: number;
  adjusted_pnl_jpy: number | null;
  adjusted_pnl_pct: number | null;
  config_missing: boolean;
  points: DashboardAssetPoint[];
};

export type DashboardPeriodPerformance = {
  bucket: string;
  decision_count: number;
  entered_count: number;
  skipped_count: number;
  conflict_count: number;
  filter_skip_count: number;
  closed_entry_count: number;
  winning_entry_count: number;
  losing_entry_count: number;
  pnl_pips: number;
  cumulative_pnl_pips: number;
  pnl_jpy: number;
  cumulative_pnl_jpy: number;
  max_dd_pips: number;
  conflict_rate: number | null;
  trade_rate: number | null;
  win_rate: number | null;
};

export type DashboardSettingPerformance = {
  setting_id: string;
  setting_labels: string[];
  decision_count: number;
  entered_count: number;
  conflict_count: number;
  closed_entry_count: number;
  winning_entry_count: number;
  pnl_pips: number;
  cumulative_pnl_pips: number;
  pnl_jpy: number;
  cumulative_pnl_jpy: number;
  max_dd_pips: number;
  conflict_rate: number | null;
  trade_rate: number | null;
  win_rate: number | null;
  expected_trade_rate: number | null;
  expected_win_rate: number | null;
  expected_annualized_pips: number | null;
  expected_cagr: number | null;
  actual_cagr: number | null;
  kill_count: number;
  last_kill_date: string | null;
  days_since_last_kill: number | null;
};

export type DashboardResponse = {
  schema: string;
  period: "all" | "year" | "month" | "week";
  at: string;
  labelMode: "all" | "include" | "exclude";
  selectedLabels: string[];
  labels: string[];
  generatedAt: string;
  asset: DashboardAsset;
  periodPerformance: DashboardPeriodPerformance[];
  settingPerformance: DashboardSettingPerformance[];
  selectedSetting: string | null;
  selectedSettingPeriodPerformance: DashboardPeriodPerformance[];
  summary: DashboardSummary[];
  events: DashboardEvent[];
};
