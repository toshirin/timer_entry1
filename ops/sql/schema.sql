create schema if not exists ops_main;
create schema if not exists ops_demo;

create table if not exists ops_main.import_cursor (
  cursor_name text primary key,
  cursor_value text not null,
  updated_at timestamptz not null default now()
);

create table if not exists ops_main.oanda_transactions_raw (
  transaction_id text primary key,
  account_id text not null,
  transaction_time timestamptz not null,
  transaction_type text not null,
  raw_json jsonb not null,
  ingested_at timestamptz not null default now()
);

create table if not exists ops_main.oanda_transactions_normalized (
  transaction_id text primary key,
  transaction_time timestamptz not null,
  transaction_type text not null,
  order_id text,
  trade_id text,
  batch_id text,
  instrument text,
  units numeric,
  price numeric,
  pl numeric,
  financing numeric,
  reason text,
  client_ext_id text,
  client_ext_tag text,
  client_ext_comment text,
  raw_transaction_id_ref text references ops_main.oanda_transactions_raw(transaction_id),
  ingested_at timestamptz not null default now()
);

create table if not exists ops_main.runtime_oanda_event_fact (
  fact_event_id text primary key,
  correlation_id text,
  decision_id text,
  execution_id text,
  setting_id text not null,
  strategy_id text,
  slot_id text,
  trade_date_local text,
  market_tz text,
  instrument text,
  side text,
  decision text,
  reason text,
  blocking_trade_id text,
  blocking_setting_id text,
  units numeric,
  requested_entry_time_local text,
  requested_entry_time_utc timestamptz,
  oanda_order_id text,
  oanda_trade_id text,
  oanda_client_id text,
  entry_transaction_id text,
  exit_transaction_id text,
  entry_at timestamptz,
  exit_at timestamptz,
  entry_price numeric,
  exit_price numeric,
  pnl_pips numeric,
  pnl_jpy numeric,
  expected_trade_rate numeric,
  actual_trade_rate numeric,
  trade_rate_delta numeric,
  expected_win_rate numeric,
  actual_win_rate numeric,
  win_rate_delta numeric,
  match_status text not null,
  status text,
  created_at timestamptz not null,
  updated_at timestamptz not null,
  synced_at timestamptz not null default now()
);

create index if not exists idx_ops_fact_setting_created
  on ops_main.runtime_oanda_event_fact (setting_id, created_at);

create index if not exists idx_ops_fact_slot_created
  on ops_main.runtime_oanda_event_fact (slot_id, created_at);

create index if not exists idx_ops_fact_correlation
  on ops_main.runtime_oanda_event_fact (correlation_id);

create or replace view ops_main.daily_setting_summary as
select
  setting_id,
  trade_date_local,
  count(*) as decision_count,
  count(*) filter (where decision = 'entered') as entered_count,
  count(*) filter (where decision like 'skipped%') as skipped_count,
  count(*) filter (where decision = 'skipped_concurrency') as conflict_count,
  case when count(*) = 0 then null else count(*) filter (where decision = 'skipped_concurrency')::numeric / count(*) end as conflict_rate,
  sum(pnl_pips) as pnl_pips,
  sum(pnl_jpy) as pnl_jpy,
  avg(expected_trade_rate) as expected_trade_rate,
  avg(actual_trade_rate) as actual_trade_rate,
  avg(expected_win_rate) as expected_win_rate,
  avg(actual_win_rate) as actual_win_rate
from ops_main.runtime_oanda_event_fact
group by setting_id, trade_date_local;

create table if not exists ops_demo.import_cursor (like ops_main.import_cursor including all);
create table if not exists ops_demo.oanda_transactions_raw (like ops_main.oanda_transactions_raw including all);
create table if not exists ops_demo.oanda_transactions_normalized (like ops_main.oanda_transactions_normalized including all);
create table if not exists ops_demo.runtime_oanda_event_fact (like ops_main.runtime_oanda_event_fact including all);

create or replace view ops_demo.daily_setting_summary as
select
  setting_id,
  trade_date_local,
  count(*) as decision_count,
  count(*) filter (where decision = 'entered') as entered_count,
  count(*) filter (where decision like 'skipped%') as skipped_count,
  count(*) filter (where decision = 'skipped_concurrency') as conflict_count,
  case when count(*) = 0 then null else count(*) filter (where decision = 'skipped_concurrency')::numeric / count(*) end as conflict_rate,
  sum(pnl_pips) as pnl_pips,
  sum(pnl_jpy) as pnl_jpy,
  avg(expected_trade_rate) as expected_trade_rate,
  avg(actual_trade_rate) as actual_trade_rate,
  avg(expected_win_rate) as expected_win_rate,
  avg(actual_win_rate) as actual_win_rate
from ops_demo.runtime_oanda_event_fact
group by setting_id, trade_date_local;
