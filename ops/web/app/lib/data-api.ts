import {
  ExecuteStatementCommand,
  Field,
  RDSDataClient
} from "@aws-sdk/client-rds-data";

type QueryResult = Record<string, string | number | boolean | null>;

function requiredEnv(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Missing required environment variable: ${name}`);
  }
  return value;
}

export function opsSchema(requested?: string | null): string {
  const schema = requested ?? process.env.OPS_WEB_SCHEMA ?? "ops_demo";
  if (schema !== "ops_main" && schema !== "ops_demo") {
    throw new Error("schema must be ops_main or ops_demo");
  }
  return schema;
}

export async function queryRows(sql: string): Promise<QueryResult[]> {
  const client = new RDSDataClient({
    region: process.env.AWS_REGION ?? process.env.AWS_DEFAULT_REGION ?? "ap-northeast-1"
  });
  const response = await client.send(
    new ExecuteStatementCommand({
      resourceArn: requiredEnv("OPS_DB_CLUSTER_ARN"),
      secretArn: requiredEnv("OPS_DB_SECRET_ARN"),
      database: process.env.OPS_DB_NAME ?? "timer_entry_ops",
      sql,
      includeResultMetadata: true
    })
  );

  const columns = (response.columnMetadata ?? []).map((column) => column.name ?? "");
  return (response.records ?? []).map((record) => {
    const row: QueryResult = {};
    record.forEach((field, index) => {
      row[columns[index]] = fieldValue(field);
    });
    return row;
  });
}

function fieldValue(field: Field): string | number | boolean | null {
  if (field.isNull) {
    return null;
  }
  if (field.stringValue !== undefined) {
    const numeric = Number(field.stringValue);
    return field.stringValue.trim() !== "" && Number.isFinite(numeric) ? numeric : field.stringValue;
  }
  if (field.longValue !== undefined) {
    return field.longValue;
  }
  if (field.doubleValue !== undefined) {
    return field.doubleValue;
  }
  if (field.booleanValue !== undefined) {
    return field.booleanValue;
  }
  return null;
}
