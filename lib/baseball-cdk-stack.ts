import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as rds from 'aws-cdk-lib/aws-rds';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as ecr from 'aws-cdk-lib/aws-ecr';
import * as events from 'aws-cdk-lib/aws-events';
import * as targets from 'aws-cdk-lib/aws-events-targets';
import * as sns from 'aws-cdk-lib/aws-sns';
import * as subscriptions from 'aws-cdk-lib/aws-sns-subscriptions';
import * as cloudwatch from 'aws-cdk-lib/aws-cloudwatch';
import * as cloudwatch_actions from 'aws-cdk-lib/aws-cloudwatch-actions';
import * as dotenv from 'dotenv';
import * as path from 'path';

// .env ファイル読み込み
dotenv.config();

export class BaseballCdkStack extends cdk.Stack {
  public readonly database: rds.DatabaseInstance;

  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // Slack Webhook URL取得
    const slackWebhookUrl = process.env.SLACK_WEBHOOK_URL;
    if (!slackWebhookUrl) {
      throw new Error('SLACK_WEBHOOK_URL is not set in .env file');
    }

    // デフォルトVPCを使用
    const vpc = ec2.Vpc.fromLookup(this, 'DefaultVPC', {
      isDefault: true,
    });

    // RDSセキュリティグループ
    const rdsSecurityGroup = new ec2.SecurityGroup(this, 'RDSSecurityGroup', {
      vpc,
      description: 'Security group for Baseball RDS',
      allowAllOutbound: true,
    });

    // インターネットからRDSへのアクセスを許可（Lambda用）
    rdsSecurityGroup.addIngressRule(
      ec2.Peer.anyIpv4(),
      ec2.Port.tcp(5432),
      'Allow from anywhere (for Lambda outside VPC)'
    );

    // RDS PostgreSQL
    const database = new rds.DatabaseInstance(this, 'BaseballDatabase', {
      engine: rds.DatabaseInstanceEngine.postgres({
        version: rds.PostgresEngineVersion.VER_15,
      }),
      instanceType: ec2.InstanceType.of(
        ec2.InstanceClass.T3,
        ec2.InstanceSize.MICRO,
      ),
      vpc,
      vpcSubnets: {
        subnetType: ec2.SubnetType.PUBLIC,
      },
      securityGroups: [rdsSecurityGroup],
      allocatedStorage: 20,
      databaseName: 'postgres',
      publiclyAccessible: true,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    this.database = database;

    // Lambda関数作成（Container Image版） - VPC外で実行
    const dataFetchFunction = new lambda.DockerImageFunction(this, 'DataFetchFunctionV3', {
      code: lambda.DockerImageCode.fromEcr(
        ecr.Repository.fromRepositoryName(this, 'BaseballLambdaRepo', 'baseball-lambda'),
        { tagOrDigest: 'v22' }
      ),
      timeout: cdk.Duration.minutes(15),
      memorySize: 3008,
      environment: {
        DB_HOST: database.dbInstanceEndpointAddress,
        DB_PORT: database.dbInstanceEndpointPort,
        DB_NAME: 'postgres',
        DB_USER: 'postgres',
        DB_PASSWORD: database.secret?.secretValueFromJson('password').unsafeUnwrap() || '',
        START_YEAR: '2015',
        END_YEAR: '2025',
        PYBASEBALL_CACHE: '/tmp/.pybaseball',
        SLACK_WEBHOOK_URL: slackWebhookUrl,
      },
    });

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