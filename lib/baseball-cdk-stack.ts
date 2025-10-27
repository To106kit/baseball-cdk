import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as rds from 'aws-cdk-lib/aws-rds';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as ecr from 'aws-cdk-lib/aws-ecr';
import * as events from 'aws-cdk-lib/aws-events';
import * as targets from 'aws-cdk-lib/aws-events-targets';

export class BaseballCdkStack extends cdk.Stack {
  public readonly database: rds.DatabaseInstance;

  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

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
        { tagOrDigest: 'v3' }
      ),
      timeout: cdk.Duration.minutes(15),
      memorySize: 1024,
      environment: {
        DB_HOST: database.dbInstanceEndpointAddress,
        DB_PORT: database.dbInstanceEndpointPort,
        DB_NAME: 'postgres',
        DB_USER: 'postgres',
        DB_PASSWORD: database.secret?.secretValueFromJson('password').unsafeUnwrap() || '',
  START_YEAR: '2015',
  END_YEAR: '2025',
        PYBASEBALL_CACHE: '/tmp/.pybaseball',
      },
    });

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

    // 出力
    new cdk.CfnOutput(this, 'LambdaFunctionName', {
      value: dataFetchFunction.functionName,
      description: 'Lambda Function Name',
    });

    new cdk.CfnOutput(this, 'LambdaFunctionArn', {
      value: dataFetchFunction.functionArn,
      description: 'Lambda Function ARN',
    });
  }
}
