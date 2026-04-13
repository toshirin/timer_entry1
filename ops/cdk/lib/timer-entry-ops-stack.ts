import * as path from "path";
import {
  CfnOutput,
  Duration,
  RemovalPolicy,
  Stack,
  StackProps,
} from "aws-cdk-lib";
import { Construct } from "constructs";
import * as dynamodb from "aws-cdk-lib/aws-dynamodb";
import * as ec2 from "aws-cdk-lib/aws-ec2";
import * as events from "aws-cdk-lib/aws-events";
import * as targets from "aws-cdk-lib/aws-events-targets";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as logs from "aws-cdk-lib/aws-logs";
import * as rds from "aws-cdk-lib/aws-rds";
import * as secretsmanager from "aws-cdk-lib/aws-secretsmanager";

export class TimerEntryOpsStack extends Stack {
  constructor(scope: Construct, id: string, props?: StackProps) {
    super(scope, id, props);

    const databaseName = process.env.OPS_DB_NAME ?? "timer_entry_ops";
    const mainSchema = process.env.OPS_MAIN_SCHEMA ?? "ops_main";
    const demoSchema = process.env.OPS_DEMO_SCHEMA ?? "ops_demo";
    const oandaSecretName = process.env.OANDA_SECRET_NAME ?? "oanda_rest_api_key";
    const decisionLogTableName = process.env.DECISION_LOG_TABLE_NAME ?? "timer-entry-runtime-decision-log";
    const executionLogTableName = process.env.EXECUTION_LOG_TABLE_NAME ?? "timer-entry-runtime-execution-log";
    const importScheduleExpression = process.env.OPS_IMPORT_SCHEDULE_EXPRESSION ?? "cron(15 22 * * ? *)";
    const auroraPostgresVersion = process.env.OPS_AURORA_POSTGRES_VERSION ?? "16.4";
    const artifactDir = path.resolve(__dirname, "../../dist");

    const vpc = new ec2.Vpc(this, "OpsVpc", {
      maxAzs: 2,
      natGateways: 0,
      subnetConfiguration: [
        {
          name: "isolated",
          subnetType: ec2.SubnetType.PRIVATE_ISOLATED,
        },
      ],
    });

    const cluster = new rds.DatabaseCluster(this, "OpsDatabase", {
      engine: rds.DatabaseClusterEngine.auroraPostgres({
        version: auroraPostgresEngineVersion(auroraPostgresVersion),
      }),
      credentials: rds.Credentials.fromGeneratedSecret("ops_admin"),
      defaultDatabaseName: databaseName,
      enableDataApi: true,
      writer: rds.ClusterInstance.serverlessV2("writer", {
        autoMinorVersionUpgrade: true,
        publiclyAccessible: false,
      }),
      serverlessV2MinCapacity: 0.5,
      serverlessV2MaxCapacity: 2,
      vpc,
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_ISOLATED },
      deletionProtection: true,
      removalPolicy: RemovalPolicy.RETAIN,
    });

    const oandaSecret = secretsmanager.Secret.fromSecretNameV2(
      this,
      "OandaSecret",
      oandaSecretName,
    );

    const decisionLogTable = dynamodb.Table.fromTableName(
      this,
      "DecisionLogTable",
      decisionLogTableName,
    );
    const executionLogTable = dynamodb.Table.fromTableName(
      this,
      "ExecutionLogTable",
      executionLogTableName,
    );

    const dailyImport = new lambda.Function(this, "DailyTransactionImport", {
      functionName: "timer-entry-ops-daily-transaction-import",
      runtime: lambda.Runtime.PYTHON_3_12,
      architecture: lambda.Architecture.X86_64,
      handler: "timer_entry_ops.daily_transaction_import.lambda_handler",
      code: lambda.Code.fromAsset(path.join(artifactDir, "daily_transaction_import.zip")),
      timeout: Duration.minutes(5),
      memorySize: 512,
      environment: {
        OPS_DB_CLUSTER_ARN: cluster.clusterArn,
        OPS_DB_SECRET_ARN: cluster.secret!.secretArn,
        OPS_DB_NAME: databaseName,
        OPS_MAIN_SCHEMA: mainSchema,
        OPS_DEMO_SCHEMA: demoSchema,
        OANDA_SECRET_NAME: oandaSecretName,
        DECISION_LOG_TABLE_NAME: decisionLogTableName,
        EXECUTION_LOG_TABLE_NAME: executionLogTableName,
        LOG_SCAN_LOOKBACK_HOURS: process.env.LOG_SCAN_LOOKBACK_HOURS ?? "36",
      },
      logRetention: logs.RetentionDays.ONE_MONTH,
    });

    cluster.grantDataApiAccess(dailyImport);
    cluster.secret!.grantRead(dailyImport);
    oandaSecret.grantRead(dailyImport);
    decisionLogTable.grantReadData(dailyImport);
    executionLogTable.grantReadData(dailyImport);

    const importRule = new events.Rule(this, "DailyImportRule", {
      ruleName: "timer-entry-ops-daily-import-rule",
      description: "Daily import for timer_entry ops",
      schedule: events.Schedule.expression(importScheduleExpression),
    });
    importRule.addTarget(new targets.LambdaFunction(dailyImport));

    new CfnOutput(this, "OpsDatabaseClusterArn", { value: cluster.clusterArn });
    new CfnOutput(this, "OpsDatabaseSecretArn", { value: cluster.secret!.secretArn });
    new CfnOutput(this, "OpsDatabaseName", { value: databaseName });
    new CfnOutput(this, "DailyImportFunctionName", { value: dailyImport.functionName });
  }
}

function auroraPostgresEngineVersion(version: string): rds.AuroraPostgresEngineVersion {
  switch (version) {
    case "15.15":
      return rds.AuroraPostgresEngineVersion.VER_15_15;
    case "16.4":
      return rds.AuroraPostgresEngineVersion.VER_16_4;
    case "16.6":
      return rds.AuroraPostgresEngineVersion.VER_16_6;
    case "16.8":
      return rds.AuroraPostgresEngineVersion.VER_16_8;
    case "16.9":
      return rds.AuroraPostgresEngineVersion.VER_16_9;
    case "16.10":
      return rds.AuroraPostgresEngineVersion.VER_16_10;
    case "16.11":
      return rds.AuroraPostgresEngineVersion.VER_16_11;
    default:
      throw new Error(`Unsupported OPS_AURORA_POSTGRES_VERSION: ${version}`);
  }
}
