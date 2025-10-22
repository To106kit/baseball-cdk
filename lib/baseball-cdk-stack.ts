import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as rds from 'aws-cdk-lib/aws-rds';
import * as iam from 'aws-cdk-lib/aws-iam';
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

    // EC2セキュリティグループ
    const ec2SecurityGroup = new ec2.SecurityGroup(this, 'EC2SecurityGroup', {
      vpc,
      description: 'Security group for Baseball EC2',
      allowAllOutbound: true,
    });

    ec2SecurityGroup.addIngressRule(
      ec2.Peer.anyIpv4(),
      ec2.Port.tcp(22),
      'Allow SSH'
    );

    ec2SecurityGroup.addIngressRule(
      ec2.Peer.anyIpv4(),
      ec2.Port.tcp(3000),
      'Allow Metabase'
    );

    // RDSセキュリティグループ
    const rdsSecurityGroup = new ec2.SecurityGroup(this, 'RDSSecurityGroup', {
      vpc,
      description: 'Security group for Baseball RDS',
      allowAllOutbound: true,
    });

    // EC2からのアクセスを許可
    rdsSecurityGroup.addIngressRule(
      ec2SecurityGroup,
      ec2.Port.tcp(5432),
      'Allow from EC2'
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

    // UserData作成（軽量化版）
    const userData = ec2.UserData.forLinux();
    userData.addCommands(
      'set -e',
      'yum update -y',
      'echo "UserData completed successfully" > /tmp/userdata-complete.txt',
    );

    // IAMロール作成
    const role = new iam.Role(this, 'EC2Role', { 
      assumedBy: new iam.ServicePrincipal('ec2.amazonaws.com'),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName('AmazonSSMManagedInstanceCore'),
      ],
    });

    // EC2インスタンス
    const instance = new ec2.Instance(this, 'BaseballEC2', {
      vpc,
      vpcSubnets: {
        subnetType: ec2.SubnetType.PUBLIC,
      },
      instanceType: ec2.InstanceType.of(
        ec2.InstanceClass.T3,
        ec2.InstanceSize.MICRO
      ),
      machineImage: ec2.MachineImage.latestAmazonLinux2023(),
      securityGroup: ec2SecurityGroup,
      keyName: 'my-key',
      userData: userData,
      role: role,
    });

    // Elastic IP
    const eip = new ec2.CfnEIP(this, 'EC2EIP', {
      domain: 'vpc',
      instanceId: instance.instanceId,
    });

    // ========================================
    // Lambda関数を追加（Container Image版）
    // ========================================

    // Lambda用セキュリティグループ
    const lambdaSecurityGroup = new ec2.SecurityGroup(this, 'LambdaSecurityGroup', {
      vpc,
      description: 'Security group for Baseball Lambda',
      allowAllOutbound: true,
    });

    // インターネットからRDSへのアクセスを許可（学習目的）
    rdsSecurityGroup.addIngressRule(
      ec2.Peer.anyIpv4(),
      ec2.Port.tcp(5432),
      'Allow from anywhere (for Lambda outside VPC)'
    );

    // Lambda関数作成（Container Image版） - VPC外で実行
    const dataFetchFunction = new lambda.DockerImageFunction(this, 'DataFetchFunctionV3', {
      code: lambda.DockerImageCode.fromEcr(
        ecr.Repository.fromRepositoryName(this, 'BaseballLambdaRepo', 'baseball-lambda'),
        { tagOrDigest: 'v3' }
      ),
      timeout: cdk.Duration.minutes(15),
      memorySize: 1024,
      // vpc, vpcSubnets, securityGroups を削除 → VPC外に
      environment: {
        DB_HOST: database.dbInstanceEndpointAddress,
        DB_PORT: database.dbInstanceEndpointPort,
        DB_NAME: 'postgres',
        DB_USER: 'postgres',
        DB_PASSWORD: database.secret?.secretValueFromJson('password').unsafeUnwrap() || '',
        START_YEAR: '2015',
        END_YEAR: '2017',
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