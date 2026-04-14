import { NextResponse } from "next/server";
import { queryRows, opsSchema } from "../../lib/data-api";
import type { DashboardEvent, DashboardSummary } from "../../lib/types";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const schema = opsSchema();
    const [summaryRows, eventRows] = await Promise.all([
      queryRows(`
        select
          setting_id,
          setting_labels::text as setting_labels,
          trade_date_local,
          decision_count,
          entered_count,
          skipped_count,
          conflict_count,
          conflict_rate,
          pnl_pips,
          pnl_jpy,
          expected_trade_rate,
          actual_trade_rate,
          expected_win_rate,
          actual_win_rate
        from ${schema}.daily_setting_summary
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
          pnl_pips,
          expected_trade_rate,
          actual_trade_rate,
          expected_win_rate,
          actual_win_rate,
          created_at
        from ${schema}.runtime_oanda_event_fact
        order by created_at desc
        limit 120
      `)
    ]);

    return NextResponse.json({
      schema,
      generatedAt: new Date().toISOString(),
      summary: summaryRows.map(withParsedLabels) as unknown as DashboardSummary[],
      events: eventRows.map(withParsedLabels) as unknown as DashboardEvent[]
    });
  } catch (error) {
    return NextResponse.json(
      {
        message: error instanceof Error ? error.message : "Unknown dashboard error"
      },
      { status: 500 }
    );
  }
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
