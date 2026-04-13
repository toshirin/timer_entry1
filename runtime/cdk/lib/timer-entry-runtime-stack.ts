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
import * as events from "aws-cdk-lib/aws-events";
import * as targets from "aws-cdk-lib/aws-events-targets";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as logs from "aws-cdk-lib/aws-logs";
import * as secretsmanager from "aws-cdk-lib/aws-secretsmanager";

export class TimerEntryRuntimeStack extends Stack {
  constructor(scope: Construct, id: string, props?: StackProps) {
    super(scope, id, props);

    const entryScheduleExpression = process.env.ENTRY_SCHEDULE_EXPRESSION ?? "cron(0/5 * * * ? *)";
    const exitScheduleExpression = process.env.EXIT_SCHEDULE_EXPRESSION ?? "cron(0/5 * * * ? *)";
    const oandaSecretName = process.env.OANDA_SECRET_NAME ?? "oanda_rest_api_key";
    const appName = "timer_entry_runtime";
    const artifactDir = path.resolve(__dirname, "../../dist");

    const settingConfigTable = new dynamodb.Table(this, "SettingConfigTable", {
      tableName: "timer-entry-runtime-setting-config",
      partitionKey: { name: "setting_id", type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      pointInTimeRecoverySpecification: { pointInTimeRecoveryEnabled: true },
      removalPolicy: RemovalPolicy.RETAIN,
    });

    settingConfigTable.addGlobalSecondaryIndex({
      indexName: "gsi_entry_trigger",
      partitionKey: { name: "trigger_bucket_entry", type: dynamodb.AttributeType.STRING },
      sortKey: { name: "setting_id", type: dynamodb.AttributeType.STRING },
      projectionType: dynamodb.ProjectionType.ALL,
    });

    settingConfigTable.addGlobalSecondaryIndex({
      indexName: "gsi_exit_trigger",
      partitionKey: { name: "trigger_bucket_exit", type: dynamodb.AttributeType.STRING },
      sortKey: { name: "setting_id", type: dynamodb.AttributeType.STRING },
      projectionType: dynamodb.ProjectionType.ALL,
    });

    const tradeStateTable = new dynamodb.Table(this, "TradeStateTable", {
      tableName: "timer-entry-runtime-trade-state",
      partitionKey: { name: "trade_id", type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      timeToLiveAttribute: "ttl",
      pointInTimeRecoverySpecification: { pointInTimeRecoveryEnabled: true },
      removalPolicy: RemovalPolicy.RETAIN,
    });

    tradeStateTable.addGlobalSecondaryIndex({
      indexName: "gsi_idempotency_key",
      partitionKey: { name: "idempotency_key", type: dynamodb.AttributeType.STRING },
      projectionType: dynamodb.ProjectionType.ALL,
    });

    tradeStateTable.addGlobalSecondaryIndex({
      indexName: "gsi_setting_status",
      partitionKey: { name: "setting_id", type: dynamodb.AttributeType.STRING },
      sortKey: { name: "status", type: dynamodb.AttributeType.STRING },
      projectionType: dynamodb.ProjectionType.ALL,
    });

    tradeStateTable.addGlobalSecondaryIndex({
      indexName: "gsi_setting_created_at",
      partitionKey: { name: "setting_id", type: dynamodb.AttributeType.STRING },
      sortKey: { name: "created_at", type: dynamodb.AttributeType.STRING },
      projectionType: dynamodb.ProjectionType.ALL,
    });

    const executionLogTable = new dynamodb.Table(this, "ExecutionLogTable", {
      tableName: "timer-entry-runtime-execution-log",
      partitionKey: { name: "execution_id", type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      pointInTimeRecoverySpecification: { pointInTimeRecoveryEnabled: true },
      removalPolicy: RemovalPolicy.RETAIN,
    });

    const decisionLogTable = new dynamodb.Table(this, "DecisionLogTable", {
      tableName: "timer-entry-runtime-decision-log",
      partitionKey: { name: "decision_id", type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      timeToLiveAttribute: "ttl",
      pointInTimeRecoverySpecification: { pointInTimeRecoveryEnabled: true },
      removalPolicy: RemovalPolicy.RETAIN,
    });

    const oandaSecret = secretsmanager.Secret.fromSecretNameV2(
      this,
      "OandaSecret",
      oandaSecretName,
    );

    const commonEnvironment = {
      APP_NAME: appName,
      MODE: "runtime",
      LOG_LEVEL: process.env.LOG_LEVEL ?? "INFO",
      OANDA_SECRET_NAME: oandaSecretName,
      SUPPORTED_MARKET_TIMEZONES: process.env.SUPPORTED_MARKET_TIMEZONES ?? "Asia/Tokyo,Europe/London",
      TRADE_STATE_TTL_DAYS: process.env.TRADE_STATE_TTL_DAYS ?? "180",
      DECISION_LOG_TTL_DAYS: process.env.DECISION_LOG_TTL_DAYS ?? "365",
      FORCED_EXIT_RETRY_COUNT: process.env.FORCED_EXIT_RETRY_COUNT ?? "3",
      BUILD_VERSION: process.env.BUILD_VERSION ?? "dev",
      SETTING_CONFIG_TABLE_NAME: settingConfigTable.tableName,
      TRADE_STATE_TABLE_NAME: tradeStateTable.tableName,
      EXECUTION_LOG_TABLE_NAME: executionLogTable.tableName,
      DECISION_LOG_TABLE_NAME: decisionLogTable.tableName,
    };

    const entryHandler = new lambda.Function(this, "EntryHandler", {
      functionName: "timer-entry-runtime-entry-handler",
      runtime: lambda.Runtime.PYTHON_3_12,
      architecture: lambda.Architecture.X86_64,
      handler: "timer_entry_runtime.handlers.entry_handler.lambda_handler",
      code: lambda.Code.fromAsset(path.join(artifactDir, "entry_handler.zip")),
      timeout: Duration.seconds(30),
      memorySize: 256,
      environment: commonEnvironment,
      logRetention: logs.RetentionDays.ONE_MONTH,
    });

    const forcedExitHandler = new lambda.Function(this, "ForcedExitHandler", {
      functionName: "timer-entry-runtime-forced-exit-handler",
      runtime: lambda.Runtime.PYTHON_3_12,
      architecture: lambda.Architecture.X86_64,
      handler: "timer_entry_runtime.handlers.forced_exit_handler.lambda_handler",
      code: lambda.Code.fromAsset(path.join(artifactDir, "forced_exit_handler.zip")),
      timeout: Duration.seconds(30),
      memorySize: 256,
      environment: commonEnvironment,
      logRetention: logs.RetentionDays.ONE_MONTH,
    });

    settingConfigTable.grantReadData(entryHandler);
    tradeStateTable.grantReadWriteData(entryHandler);
    executionLogTable.grantReadWriteData(entryHandler);
    decisionLogTable.grantWriteData(entryHandler);
    oandaSecret.grantRead(entryHandler);

    settingConfigTable.grantReadData(forcedExitHandler);
    tradeStateTable.grantReadWriteData(forcedExitHandler);
    executionLogTable.grantReadWriteData(forcedExitHandler);
    decisionLogTable.grantWriteData(forcedExitHandler);
    oandaSecret.grantRead(forcedExitHandler);

    const entryRule = new events.Rule(this, "EntryRule", {
      ruleName: "timer-entry-runtime-entry-rule",
      description: "Entry trigger for timer_entry_runtime",
      schedule: events.Schedule.expression(entryScheduleExpression),
    });
    entryRule.addTarget(new targets.LambdaFunction(entryHandler));

    const exitRule = new events.Rule(this, "ExitRule", {
      ruleName: "timer-entry-runtime-exit-rule",
      description: "Forced exit trigger for timer_entry_runtime",
      schedule: events.Schedule.expression(exitScheduleExpression),
    });
    exitRule.addTarget(new targets.LambdaFunction(forcedExitHandler));

    new CfnOutput(this, "SettingConfigTableName", { value: settingConfigTable.tableName });
    new CfnOutput(this, "TradeStateTableName", { value: tradeStateTable.tableName });
    new CfnOutput(this, "ExecutionLogTableName", { value: executionLogTable.tableName });
    new CfnOutput(this, "DecisionLogTableName", { value: decisionLogTable.tableName });
    new CfnOutput(this, "EntryFunctionName", { value: entryHandler.functionName });
    new CfnOutput(this, "ForcedExitFunctionName", { value: forcedExitHandler.functionName });
  }
}

