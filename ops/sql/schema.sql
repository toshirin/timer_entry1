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
  account_id text,
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
  account_balance numeric,
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
  setting_labels jsonb not null default '[]'::jsonb,
  trade_date_local text,
  market_tz text,
  instrument text,
  side text,
  decision text,
  reason text,
  blocking_trade_id text,
  blocking_setting_id text,
  units numeric,
  sizing_basis text,
  account_balance numeric,
  effective_margin_ratio numeric,
  estimated_margin_ratio_after_entry numeric,
  margin_price numeric,
  margin_price_side text,
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

alter table ops_main.runtime_oanda_event_fact
  add column if not exists setting_labels jsonb not null default '[]'::jsonb;

alter table ops_main.oanda_transactions_normalized
  add column if not exists account_id text,
  add column if not exists account_balance numeric;

alter table ops_main.runtime_oanda_event_fact
  add column if not exists sizing_basis text,
  add column if not exists account_balance numeric,
  add column if not exists effective_margin_ratio numeric,
  add column if not exists estimated_margin_ratio_after_entry numeric,
  add column if not exists margin_price numeric,
  add column if not exists margin_price_side text;

create index if not exists idx_ops_fact_setting_created
  on ops_main.runtime_oanda_event_fact (setting_id, created_at);

create index if not exists idx_ops_fact_slot_created
  on ops_main.runtime_oanda_event_fact (slot_id, created_at);

create index if not exists idx_ops_fact_correlation
  on ops_main.runtime_oanda_event_fact (correlation_id);

create index if not exists idx_ops_normalized_trade
  on ops_main.oanda_transactions_normalized (trade_id);

create index if not exists idx_ops_normalized_order
  on ops_main.oanda_transactions_normalized (order_id);

create index if not exists idx_ops_normalized_client_ext
  on ops_main.oanda_transactions_normalized (client_ext_id);

create or replace view ops_main.oanda_latest_account_balance as
select distinct on (account_id)
  account_id,
  account_balance,
  transaction_id,
  transaction_time
from ops_main.oanda_transactions_normalized
where account_id is not null
  and account_balance is not null
order by account_id, transaction_time desc, transaction_id desc;

drop view if exists ops_main.daily_setting_summary;

create or replace view ops_main.daily_setting_summary as
select
  setting_id,
  setting_labels,
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
group by setting_id, setting_labels, trade_date_local;

create table if not exists ops_demo.import_cursor (like ops_main.import_cursor including all);
create table if not exists ops_demo.oanda_transactions_raw (like ops_main.oanda_transactions_raw including all);
create table if not exists ops_demo.oanda_transactions_normalized (like ops_main.oanda_transactions_normalized including all);
create table if not exists ops_demo.runtime_oanda_event_fact (like ops_main.runtime_oanda_event_fact including all);

alter table ops_demo.runtime_oanda_event_fact
  add column if not exists setting_labels jsonb not null default '[]'::jsonb;

alter table ops_demo.oanda_transactions_normalized
  add column if not exists account_id text,
  add column if not exists account_balance numeric;

alter table ops_demo.runtime_oanda_event_fact
  add column if not exists sizing_basis text,
  add column if not exists account_balance numeric,
  add column if not exists effective_margin_ratio numeric,
  add column if not exists estimated_margin_ratio_after_entry numeric,
  add column if not exists margin_price numeric,
  add column if not exists margin_price_side text;

drop view if exists ops_demo.daily_setting_summary;

create or replace view ops_demo.daily_setting_summary as
select
  setting_id,
  setting_labels,
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
group by setting_id, setting_labels, trade_date_local;

create or replace view ops_demo.oanda_latest_account_balance as
select distinct on (account_id)
  account_id,
  account_balance,
  transaction_id,
  transaction_time
from ops_demo.oanda_transactions_normalized
where account_id is not null
  and account_balance is not null
order by account_id, transaction_time desc, transaction_id desc;
