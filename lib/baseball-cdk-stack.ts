import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as ecr from 'aws-cdk-lib/aws-ecr';
import * as events from 'aws-cdk-lib/aws-events';
import * as targets from 'aws-cdk-lib/aws-events-targets';
import * as sns from 'aws-cdk-lib/aws-sns';
import * as subscriptions from 'aws-cdk-lib/aws-sns-subscriptions';
import * as cloudwatch from 'aws-cdk-lib/aws-cloudwatch';
import * as cloudwatch_actions from 'aws-cdk-lib/aws-cloudwatch-actions';
import * as glue from 'aws-cdk-lib/aws-glue';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as dotenv from 'dotenv';
import * as path from 'path';

// .env ファイル読み込み
dotenv.config();

export class BaseballCdkStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // Slack Webhook URL取得
    const slackWebhookUrl = process.env.SLACK_WEBHOOK_URL;
    if (!slackWebhookUrl) {
      throw new Error('SLACK_WEBHOOK_URL is not set in .env file');
    }

    // S3バケット作成（Data Lake）
    const dataBucket = new s3.Bucket(this, 'BaseballDataBucket', {
      bucketName: `baseball-stats-data-${this.account}`,
      encryption: s3.BucketEncryption.S3_MANAGED,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      removalPolicy: cdk.RemovalPolicy.RETAIN, // データ保護のため削除しない
      lifecycleRules: [
        {
          id: 'TransitionToIA',
          transitions: [
            {
              storageClass: s3.StorageClass.INTELLIGENT_TIERING,
              transitionAfter: cdk.Duration.days(90),
            },
          ],
        },
      ],
    });

    // Glue Database（Athenaスキーマ用）
    const glueDatabase = new glue.CfnDatabase(this, 'BaseballDatabase', {
      catalogId: this.account,
      databaseInput: {
        name: 'baseball_stats',
        description: 'Baseball statistics data lake',
      },
    });

    // Glue Table（Athenaクエリ用）
    const glueTable = new glue.CfnTable(this, 'BattingStatsTable', {
      catalogId: this.account,
      databaseName: glueDatabase.ref,
      tableInput: {
        name: 'batting_stats',
        description: 'MLB batting statistics by year',
        tableType: 'EXTERNAL_TABLE',
        partitionKeys: [
          {
            name: 'year',
            type: 'int',
            comment: 'Season year',
          },
        ],
        storageDescriptor: {
          columns: [
            { name: 'name', type: 'string', comment: 'Player name' },
            { name: 'season', type: 'int', comment: 'Season year' },
            { name: 'games', type: 'int', comment: 'Games played' },
            { name: 'at_bats', type: 'int', comment: 'At bats' },
            { name: 'runs', type: 'int', comment: 'Runs scored' },
            { name: 'hits', type: 'int', comment: 'Hits' },
            { name: 'hr', type: 'int', comment: 'Home runs' },
            { name: 'rbi', type: 'int', comment: 'Runs batted in' },
            { name: 'sb', type: 'int', comment: 'Stolen bases' },
            { name: 'avg', type: 'double', comment: 'Batting average' },
            { name: 'created_at', type: 'timestamp', comment: 'Record creation timestamp' },
          ],
          location: `s3://${dataBucket.bucketName}/batting_stats/`,
          inputFormat: 'org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat',
          outputFormat: 'org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat',
          serdeInfo: {
            serializationLibrary: 'org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe',
          },
        },
      },
    });
    glueTable.addDependency(glueDatabase);

    // Glue Table（投手成績用）
    const gluePitchingTable = new glue.CfnTable(this, 'PitchingStatsTable', {
      catalogId: this.account,
      databaseName: glueDatabase.ref,
      tableInput: {
        name: 'pitching_stats',
        description: 'MLB pitching statistics by year',
        tableType: 'EXTERNAL_TABLE',
        partitionKeys: [
          {
            name: 'year',
            type: 'int',
            comment: 'Season year',
          },
        ],
        storageDescriptor: {
          columns: [
            { name: 'name', type: 'string', comment: 'Pitcher name' },
            { name: 'season', type: 'int', comment: 'Season year' },
            { name: 'games', type: 'int', comment: 'Games pitched' },
            { name: 'wins', type: 'int', comment: 'Wins' },
            { name: 'losses', type: 'int', comment: 'Losses' },
            { name: 'era', type: 'double', comment: 'Earned run average' },
            { name: 'strikeouts', type: 'int', comment: 'Strikeouts' },
            { name: 'innings_pitched', type: 'double', comment: 'Innings pitched' },
            { name: 'whip', type: 'double', comment: 'WHIP (walks + hits per inning)' },
            { name: 'created_at', type: 'timestamp', comment: 'Record creation timestamp' },
          ],
          location: `s3://${dataBucket.bucketName}/pitching_stats/`,
          inputFormat: 'org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat',
          outputFormat: 'org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat',
          serdeInfo: {
            serializationLibrary: 'org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe',
          },
        },
      },
    });
    gluePitchingTable.addDependency(glueDatabase);

    // Lambda関数作成（Container Image版） - VPC外で実行
    const dataFetchFunction = new lambda.DockerImageFunction(this, 'DataFetchFunctionV3', {
      code: lambda.DockerImageCode.fromEcr(
        ecr.Repository.fromRepositoryName(this, 'BaseballLambdaRepo', 'baseball-lambda'),
        { tagOrDigest: 'v30' }
      ),
      timeout: cdk.Duration.minutes(15),
      memorySize: 3008,
      environment: {
        S3_BUCKET: dataBucket.bucketName,
        START_YEAR: '2015',
        END_YEAR: '2025',
        PYBASEBALL_CACHE: '/tmp/.pybaseball',
        SLACK_WEBHOOK_URL: slackWebhookUrl,
      },
    });

    // Lambdaに S3 書き込み権限付与
    dataBucket.grantWrite(dataFetchFunction);

    // ==========================================
    // SNS Topic (アラーム通知用)
    // ==========================================
    const alarmTopic = new sns.Topic(this, 'BaseballAlarmTopic', {
      displayName: 'Baseball DB CloudWatch Alarms',
      topicName: 'baseball-db-alarms',
    });

    // ==========================================
    // Slack通知Lambda関数
    // ==========================================
    const slackNotifierFunction = new lambda.Function(this, 'SlackNotifierFunction', {
      runtime: lambda.Runtime.PYTHON_3_9,
      handler: 'index.lambda_handler',
      code: lambda.Code.fromAsset(path.join(__dirname, '../lambda/slack-notifier')),
      timeout: cdk.Duration.seconds(30),
      environment: {
        SLACK_WEBHOOK_URL: slackWebhookUrl,
      },
    });

    // SNS TopicにSlack通知Lambda購読
    alarmTopic.addSubscription(new subscriptions.LambdaSubscription(slackNotifierFunction));

    // ==========================================
    // CloudWatch Alarms
    // ==========================================

    // 1. Lambda エラー監視
    const lambdaErrorAlarm = new cloudwatch.Alarm(this, 'LambdaErrorAlarm', {
      metric: dataFetchFunction.metricErrors({
        period: cdk.Duration.minutes(5),
        statistic: 'Sum',
      }),
      threshold: 1,
      evaluationPeriods: 1,
      comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
      alarmName: 'Baseball-Lambda-Errors',
      alarmDescription: 'Baseball data fetch Lambda function has errors',
      treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
    });
    lambdaErrorAlarm.addAlarmAction(new cloudwatch_actions.SnsAction(alarmTopic));
    lambdaErrorAlarm.addOkAction(new cloudwatch_actions.SnsAction(alarmTopic));

    // 2. Lambda タイムアウト監視
    const lambdaTimeoutAlarm = new cloudwatch.Alarm(this, 'LambdaTimeoutAlarm', {
      metric: dataFetchFunction.metricDuration({
        period: cdk.Duration.minutes(5),
        statistic: 'Maximum',
      }),
      threshold: 14 * 60 * 1000, // 14分 (タイムアウト15分の少し前)
      evaluationPeriods: 1,
      comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
      alarmName: 'Baseball-Lambda-Timeout-Warning',
      alarmDescription: 'Baseball Lambda is approaching timeout (14+ minutes)',
      treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
    });
    lambdaTimeoutAlarm.addAlarmAction(new cloudwatch_actions.SnsAction(alarmTopic));
    lambdaTimeoutAlarm.addOkAction(new cloudwatch_actions.SnsAction(alarmTopic));

    // 3. Lambda スロットリング監視
    const lambdaThrottleAlarm = new cloudwatch.Alarm(this, 'LambdaThrottleAlarm', {
      metric: dataFetchFunction.metricThrottles({
        period: cdk.Duration.minutes(5),
        statistic: 'Sum',
      }),
      threshold: 1,
      evaluationPeriods: 1,
      comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
      alarmName: 'Baseball-Lambda-Throttles',
      alarmDescription: 'Baseball Lambda is being throttled',
      treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
    });
    lambdaThrottleAlarm.addAlarmAction(new cloudwatch_actions.SnsAction(alarmTopic));
    lambdaThrottleAlarm.addOkAction(new cloudwatch_actions.SnsAction(alarmTopic));

    // EventBridge ルール: 毎週日曜 0時 (UTC)
    const rule = new events.Rule(this, 'WeeklyScheduleRule', {
      schedule: events.Schedule.cron({
        weekDay: 'SUN',
        hour: '0',
        minute: '0',
      }),
      description: 'Run baseball data fetch every Sunday at midnight UTC',
    });

    // Lambda関数をターゲットに設定
    rule.addTarget(new targets.LambdaFunction(dataFetchFunction));

    // ==========================================
    // Outputs
    // ==========================================
    new cdk.CfnOutput(this, 'DataBucketName', {
      value: dataBucket.bucketName,
      description: 'S3 Data Lake Bucket Name',
    });

    new cdk.CfnOutput(this, 'GlueDatabaseName', {
      value: glueDatabase.ref,
      description: 'Glue Database Name for Athena',
    });

    new cdk.CfnOutput(this, 'AthenaQueryExample', {
      value: `SELECT * FROM ${glueDatabase.ref}.batting_stats WHERE year = 2024 LIMIT 10;`,
      description: 'Example Athena SQL Query',
    });

    new cdk.CfnOutput(this, 'LambdaFunctionName', {
      value: dataFetchFunction.functionName,
      description: 'Lambda Function Name',
    });

    new cdk.CfnOutput(this, 'LambdaFunctionArn', {
      value: dataFetchFunction.functionArn,
      description: 'Lambda Function ARN',
    });

    new cdk.CfnOutput(this, 'SNSTopicArn', {
      value: alarmTopic.topicArn,
      description: 'SNS Topic ARN for CloudWatch Alarms',
    });

    new cdk.CfnOutput(this, 'SlackNotifierFunctionName', {
      value: slackNotifierFunction.functionName,
      description: 'Slack Notifier Lambda Function Name',
    });
  }
}