export type DashboardSummary = {
  setting_id: string;
  trade_date_local: string;
  decision_count: number;
  entered_count: number;
  skipped_count: number;
  conflict_count: number;
  conflict_rate: number | null;
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
  slot_id: string | null;
  trade_date_local: string | null;
  decision: string | null;
  reason: string | null;
  match_status: string | null;
  pnl_pips: number | null;
  expected_trade_rate: number | null;
  actual_trade_rate: number | null;
  expected_win_rate: number | null;
  actual_win_rate: number | null;
  created_at: string;
};

export type DashboardResponse = {
  schema: string;
  generatedAt: string;
  summary: DashboardSummary[];
  events: DashboardEvent[];
};
