truncate table ops_demo.runtime_oanda_event_fact;
truncate table ops_demo.oanda_transactions_normalized;
truncate table ops_demo.oanda_transactions_raw;
truncate table ops_demo.import_cursor;

insert into ops_demo.import_cursor (cursor_name, cursor_value, updated_at)
values ('oanda_last_transaction_id', '900100', now());

insert into ops_demo.runtime_oanda_event_fact (
  fact_event_id,
  correlation_id,
  decision_id,
  setting_id,
  strategy_id,
  slot_id,
  trade_date_local,
  market_tz,
  instrument,
  side,
  decision,
  reason,
  blocking_trade_id,
  blocking_setting_id,
  entry_at,
  exit_at,
  entry_price,
  exit_price,
  pnl_pips,
  pnl_jpy,
  expected_trade_rate,
  actual_trade_rate,
  trade_rate_delta,
  expected_win_rate,
  actual_win_rate,
  win_rate_delta,
  match_status,
  status,
  created_at,
  updated_at
)
values
  ('demo-001', 'demo-tyo09-001', 'demo-decision-001', 'tyo09_sell_runtime_v1', 'timed_entry_sell', 'tyo09', '2026-04-06', 'Asia/Tokyo', 'USD_JPY', 'sell', 'entered', null, null, null, '2026-04-06T00:35:03Z', '2026-04-06T01:20:01Z', 151.210, 150.980, 23.0, 2300, 0.400659, 0.380000, -0.020659, 0.517808, 1.000000, 0.482192, 'matched', 'exited', '2026-04-06T00:35:03Z', '2026-04-06T01:20:01Z'),
  ('demo-002', 'demo-tyo09-002', 'demo-decision-002', 'tyo09_sell_runtime_v1', 'timed_entry_sell', 'tyo09', '2026-04-07', 'Asia/Tokyo', 'USD_JPY', 'sell', 'entered', null, null, null, '2026-04-07T00:35:02Z', '2026-04-07T01:20:00Z', 151.020, 151.260, -24.0, -2400, 0.400659, 0.390000, -0.010659, 0.517808, 0.500000, -0.017808, 'matched', 'exited', '2026-04-07T00:35:02Z', '2026-04-07T01:20:00Z'),
  ('demo-003', 'demo-tyo09-003', 'demo-decision-003', 'tyo09_sell_runtime_v1', 'timed_entry_sell', 'tyo09', '2026-04-08', 'Asia/Tokyo', 'USD_JPY', 'sell', 'skipped_concurrency', 'open_position_limit_reached', 'oanda-trade-778', 'lon15_buy_runtime_v1', null, null, null, null, null, null, 0.400659, 0.250000, -0.150659, 0.517808, 0.500000, -0.017808, 'decision_only', 'skipped_concurrency', '2026-04-08T00:35:01Z', '2026-04-08T00:35:01Z'),
  ('demo-004', 'demo-lon15-001', 'demo-decision-004', 'lon15_buy_runtime_v1', 'timed_entry_buy', 'lon15', '2026-04-06', 'Europe/London', 'USD_JPY', 'buy', 'entered', null, null, null, '2026-04-06T14:40:01Z', '2026-04-06T15:45:01Z', 150.650, 150.830, 18.0, 1800, 0.419604, 0.420000, 0.000396, 0.577428, 1.000000, 0.422572, 'matched', 'exited', '2026-04-06T14:40:01Z', '2026-04-06T15:45:01Z'),
  ('demo-005', 'demo-lon15-002', 'demo-decision-005', 'lon15_buy_runtime_v1', 'timed_entry_buy', 'lon15', '2026-04-07', 'Europe/London', 'USD_JPY', 'buy', 'entered', null, null, null, '2026-04-07T14:40:03Z', '2026-04-07T15:45:01Z', 150.920, 150.700, -22.0, -2200, 0.419604, 0.430000, 0.010396, 0.577428, 0.500000, -0.077428, 'matched', 'exited', '2026-04-07T14:40:03Z', '2026-04-07T15:45:01Z'),
  ('demo-006', 'demo-lon15-003', 'demo-decision-006', 'lon15_buy_runtime_v1', 'timed_entry_buy', 'lon15', '2026-04-08', 'Europe/London', 'USD_JPY', 'buy', 'skipped_kill_switch', 'drawdown_threshold_breached', null, null, null, null, null, null, null, null, 0.419604, 0.100000, -0.319604, 0.577428, 0.400000, -0.177428, 'decision_only', 'skipped_kill_switch', '2026-04-08T14:40:01Z', '2026-04-08T14:40:01Z'),
  ('demo-007', 'demo-orphan-oanda-001', null, 'unknown_oanda_only', null, null, '2026-04-08', 'Asia/Tokyo', 'USD_JPY', null, null, 'oanda_only', null, null, '2026-04-08T02:00:00Z', null, 151.000, null, null, null, null, null, null, null, null, null, 'oanda_only', 'orphan', '2026-04-08T02:00:00Z', '2026-04-08T02:00:00Z');
