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
  broker_trade_date text,
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
  exit_reason text,
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

create table if not exists ops_main.setting_metadata (
  setting_id text primary key,
  enabled boolean not null default false,
  strategy_id text,
  slot_id text,
  setting_labels jsonb not null default '[]'::jsonb,
  market_session text,
  market_tz text,
  instrument text,
  side text,
  entry_clock_local text,
  forced_exit_clock_local text,
  fixed_units numeric,
  margin_ratio_target numeric,
  size_scale_pct numeric,
  unit_level integer,
  unit_level_policy_name text,
  unit_level_policy_version text,
  unit_level_updated_at timestamptz,
  unit_level_updated_by text,
  unit_level_decision_month text,
  tp_pips numeric,
  sl_pips numeric,
  research_label text,
  kill_switch_dd_pct numeric,
  kill_switch_reference_balance_jpy numeric,
  min_maintenance_margin_pct numeric,
  filter_spec_json jsonb,
  execution_spec_json jsonb,
  expected_trade_rate numeric,
  expected_win_rate numeric,
  expected_annualized_pips numeric,
  expected_cagr numeric,
  source_file text,
  imported_at timestamptz not null default now(),
  raw_config jsonb not null
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
  add column if not exists margin_price_side text,
  add column if not exists exit_reason text,
  add column if not exists broker_trade_date text;

alter table ops_main.setting_metadata
  add column if not exists enabled boolean not null default false,
  add column if not exists setting_labels jsonb not null default '[]'::jsonb,
  add column if not exists market_session text,
  add column if not exists market_tz text,
  add column if not exists instrument text,
  add column if not exists side text,
  add column if not exists entry_clock_local text,
  add column if not exists forced_exit_clock_local text,
  add column if not exists fixed_units numeric,
  add column if not exists margin_ratio_target numeric,
  add column if not exists size_scale_pct numeric,
  add column if not exists unit_level integer,
  add column if not exists unit_level_policy_name text,
  add column if not exists unit_level_policy_version text,
  add column if not exists unit_level_updated_at timestamptz,
  add column if not exists unit_level_updated_by text,
  add column if not exists unit_level_decision_month text,
  add column if not exists tp_pips numeric,
  add column if not exists sl_pips numeric,
  add column if not exists research_label text,
  add column if not exists kill_switch_dd_pct numeric,
  add column if not exists kill_switch_reference_balance_jpy numeric,
  add column if not exists min_maintenance_margin_pct numeric,
  add column if not exists filter_spec_json jsonb,
  add column if not exists execution_spec_json jsonb,
  add column if not exists expected_trade_rate numeric,
  add column if not exists expected_win_rate numeric,
  add column if not exists expected_annualized_pips numeric,
  add column if not exists expected_cagr numeric,
  add column if not exists source_file text,
  add column if not exists imported_at timestamptz not null default now(),
  add column if not exists raw_config jsonb not null default '{}'::jsonb;

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

create index if not exists idx_ops_setting_metadata_slot
  on ops_main.setting_metadata (slot_id);

create table if not exists ops_main.unit_level_decision_log (
  decision_log_id text primary key,
  setting_id text not null,
  strategy_id text,
  slot_id text,
  instrument text,
  market_session text,
  decision_month text not null,
  policy_name text not null,
  policy_version text not null,
  labels jsonb not null default '[]'::jsonb,
  source text not null,
  current_level integer not null,
  next_level integer not null,
  current_units numeric,
  threshold_jpy numeric,
  cum_jpy_month numeric,
  latest_equity_jpy numeric,
  unit_basis text,
  closed_trade_count integer not null default 0,
  decision text not null,
  decision_reason text not null,
  applied boolean not null default false,
  duplicate boolean not null default false,
  applied_at timestamptz,
  created_at timestamptz not null default now()
);

alter table ops_main.unit_level_decision_log
  add column if not exists strategy_id text,
  add column if not exists slot_id text,
  add column if not exists instrument text,
  add column if not exists market_session text,
  add column if not exists labels jsonb not null default '[]'::jsonb,
  add column if not exists current_units numeric,
  add column if not exists threshold_jpy numeric,
  add column if not exists cum_jpy_month numeric,
  add column if not exists latest_equity_jpy numeric,
  add column if not exists unit_basis text,
  add column if not exists closed_trade_count integer not null default 0,
  add column if not exists duplicate boolean not null default false,
  add column if not exists applied_at timestamptz,
  add column if not exists created_at timestamptz not null default now();

create index if not exists idx_ops_unit_level_decision_setting_month
  on ops_main.unit_level_decision_log (setting_id, decision_month);

create index if not exists idx_ops_unit_level_decision_created_at
  on ops_main.unit_level_decision_log (created_at);

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
with decision_summary as (
  select
    coalesce(
      nullif(correlation_id, ''),
      nullif(concat_ws('#', setting_id, broker_trade_date, decision, reason), ''),
      nullif(decision_id, ''),
      fact_event_id
    ) as logical_event_id,
    max(setting_id) as setting_id,
    max(setting_labels::text)::jsonb as setting_labels,
    coalesce(
      min(broker_trade_date) filter (where decision <> 'exited'),
      min(broker_trade_date)
    ) as broker_trade_date,
    bool_or(decision is not null and decision not in ('exited', 'oanda_only', 'skipped_no_entered_state')) as has_primary_decision,
    bool_or(decision = 'entered') as has_entered,
    bool_or(decision like 'skipped%') as has_skipped,
    bool_or(decision = 'skipped_concurrency') as has_conflict,
    bool_or(decision = 'skipped_filter' or reason = 'filter_rejected') as has_filter_skip,
    max(pnl_pips) filter (where pnl_pips is not null) as pnl_pips,
    max(pnl_jpy) filter (where pnl_pips is not null) as pnl_jpy,
    avg(expected_trade_rate) as expected_trade_rate,
    avg(actual_trade_rate) as actual_trade_rate,
    avg(expected_win_rate) as expected_win_rate,
    avg(actual_win_rate) as actual_win_rate
  from ops_main.runtime_oanda_event_fact
  where coalesce(
      nullif(correlation_id, ''),
      nullif(concat_ws('#', setting_id, broker_trade_date, decision, reason), ''),
      nullif(decision_id, ''),
      fact_event_id
    ) is not null
  group by logical_event_id
)
select
  setting_id,
  setting_labels,
  broker_trade_date,
  count(*) as decision_count,
  count(*) filter (where has_entered) as entered_count,
  count(*) filter (where has_skipped) as skipped_count,
  count(*) filter (where has_conflict) as conflict_count,
  count(*) filter (where has_filter_skip) as filter_skip_count,
  count(*) filter (where pnl_pips is not null) as closed_entry_count,
  count(*) filter (where pnl_pips > 0) as winning_entry_count,
  case
    when count(*) = 0 then null
    else count(*) filter (where has_conflict)::numeric / count(*)
  end as conflict_rate,
  case
    when count(*) = 0 then null
    else count(*) filter (where has_entered)::numeric / count(*)
  end as trade_rate,
  case
    when count(*) filter (where pnl_pips is not null) = 0 then null
    else count(*) filter (where pnl_pips > 0)::numeric
      / count(*) filter (where pnl_pips is not null)
  end as win_rate,
  sum(pnl_pips) as pnl_pips,
  sum(pnl_jpy) filter (where pnl_pips is not null) as pnl_jpy,
  avg(expected_trade_rate) as expected_trade_rate,
  avg(actual_trade_rate) as actual_trade_rate,
  avg(expected_win_rate) as expected_win_rate,
  avg(actual_win_rate) as actual_win_rate
from decision_summary
where has_primary_decision
  and broker_trade_date is not null
  and extract(isodow from broker_trade_date::date) between 1 and 5
group by setting_id, setting_labels, broker_trade_date;

create table if not exists ops_demo.import_cursor (like ops_main.import_cursor including all);
create table if not exists ops_demo.oanda_transactions_raw (like ops_main.oanda_transactions_raw including all);
create table if not exists ops_demo.oanda_transactions_normalized (like ops_main.oanda_transactions_normalized including all);
create table if not exists ops_demo.runtime_oanda_event_fact (like ops_main.runtime_oanda_event_fact including all);
create table if not exists ops_demo.setting_metadata (like ops_main.setting_metadata including all);
create table if not exists ops_demo.unit_level_decision_log (like ops_main.unit_level_decision_log including all);

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
  add column if not exists margin_price_side text,
  add column if not exists exit_reason text,
  add column if not exists broker_trade_date text;

alter table ops_demo.setting_metadata
  add column if not exists enabled boolean not null default false,
  add column if not exists setting_labels jsonb not null default '[]'::jsonb,
  add column if not exists market_session text,
  add column if not exists market_tz text,
  add column if not exists instrument text,
  add column if not exists side text,
  add column if not exists entry_clock_local text,
  add column if not exists forced_exit_clock_local text,
  add column if not exists fixed_units numeric,
  add column if not exists margin_ratio_target numeric,
  add column if not exists size_scale_pct numeric,
  add column if not exists unit_level integer,
  add column if not exists unit_level_policy_name text,
  add column if not exists unit_level_policy_version text,
  add column if not exists unit_level_updated_at timestamptz,
  add column if not exists unit_level_updated_by text,
  add column if not exists unit_level_decision_month text,
  add column if not exists tp_pips numeric,
  add column if not exists sl_pips numeric,
  add column if not exists research_label text,
  add column if not exists kill_switch_dd_pct numeric,
  add column if not exists kill_switch_reference_balance_jpy numeric,
  add column if not exists min_maintenance_margin_pct numeric,
  add column if not exists filter_spec_json jsonb,
  add column if not exists execution_spec_json jsonb,
  add column if not exists expected_trade_rate numeric,
  add column if not exists expected_win_rate numeric,
  add column if not exists expected_annualized_pips numeric,
  add column if not exists expected_cagr numeric,
  add column if not exists source_file text,
  add column if not exists imported_at timestamptz not null default now(),
  add column if not exists raw_config jsonb not null default '{}'::jsonb;

alter table ops_demo.unit_level_decision_log
  add column if not exists strategy_id text,
  add column if not exists slot_id text,
  add column if not exists instrument text,
  add column if not exists market_session text,
  add column if not exists labels jsonb not null default '[]'::jsonb,
  add column if not exists current_units numeric,
  add column if not exists threshold_jpy numeric,
  add column if not exists cum_jpy_month numeric,
  add column if not exists latest_equity_jpy numeric,
  add column if not exists unit_basis text,
  add column if not exists closed_trade_count integer not null default 0,
  add column if not exists duplicate boolean not null default false,
  add column if not exists applied_at timestamptz,
  add column if not exists created_at timestamptz not null default now();

create index if not exists idx_ops_demo_unit_level_decision_setting_month
  on ops_demo.unit_level_decision_log (setting_id, decision_month);

create index if not exists idx_ops_demo_unit_level_decision_created_at
  on ops_demo.unit_level_decision_log (created_at);

drop view if exists ops_demo.daily_setting_summary;

create or replace view ops_demo.daily_setting_summary as
with decision_summary as (
  select
    coalesce(
      nullif(correlation_id, ''),
      nullif(concat_ws('#', setting_id, broker_trade_date, decision, reason), ''),
      nullif(decision_id, ''),
      fact_event_id
    ) as logical_event_id,
    max(setting_id) as setting_id,
    max(setting_labels::text)::jsonb as setting_labels,
    coalesce(
      min(broker_trade_date) filter (where decision <> 'exited'),
      min(broker_trade_date)
    ) as broker_trade_date,
    bool_or(decision is not null and decision not in ('exited', 'oanda_only', 'skipped_no_entered_state')) as has_primary_decision,
    bool_or(decision = 'entered') as has_entered,
    bool_or(decision like 'skipped%') as has_skipped,
    bool_or(decision = 'skipped_concurrency') as has_conflict,
    bool_or(decision = 'skipped_filter' or reason = 'filter_rejected') as has_filter_skip,
    max(pnl_pips) filter (where pnl_pips is not null) as pnl_pips,
    max(pnl_jpy) filter (where pnl_pips is not null) as pnl_jpy,
    avg(expected_trade_rate) as expected_trade_rate,
    avg(actual_trade_rate) as actual_trade_rate,
    avg(expected_win_rate) as expected_win_rate,
    avg(actual_win_rate) as actual_win_rate
  from ops_demo.runtime_oanda_event_fact
  where coalesce(
      nullif(correlation_id, ''),
      nullif(concat_ws('#', setting_id, broker_trade_date, decision, reason), ''),
      nullif(decision_id, ''),
      fact_event_id
    ) is not null
  group by logical_event_id
)
select
  setting_id,
  setting_labels,
  broker_trade_date,
  count(*) as decision_count,
  count(*) filter (where has_entered) as entered_count,
  count(*) filter (where has_skipped) as skipped_count,
  count(*) filter (where has_conflict) as conflict_count,
  count(*) filter (where has_filter_skip) as filter_skip_count,
  count(*) filter (where pnl_pips is not null) as closed_entry_count,
  count(*) filter (where pnl_pips > 0) as winning_entry_count,
  case
    when count(*) = 0 then null
    else count(*) filter (where has_conflict)::numeric / count(*)
  end as conflict_rate,
  case
    when count(*) = 0 then null
    else count(*) filter (where has_entered)::numeric / count(*)
  end as trade_rate,
  case
    when count(*) filter (where pnl_pips is not null) = 0 then null
    else count(*) filter (where pnl_pips > 0)::numeric
      / count(*) filter (where pnl_pips is not null)
  end as win_rate,
  sum(pnl_pips) as pnl_pips,
  sum(pnl_jpy) filter (where pnl_pips is not null) as pnl_jpy,
  avg(expected_trade_rate) as expected_trade_rate,
  avg(actual_trade_rate) as actual_trade_rate,
  avg(expected_win_rate) as expected_win_rate,
  avg(actual_win_rate) as actual_win_rate
from decision_summary
where has_primary_decision
  and broker_trade_date is not null
  and extract(isodow from broker_trade_date::date) between 1 and 5
group by setting_id, setting_labels, broker_trade_date;

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
