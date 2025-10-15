import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as rds from 'aws-cdk-lib/aws-rds';
import * as iam from 'aws-cdk-lib/aws-iam';

export class BaseballCdkStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // デフォルトVPCを使用（Phase1と同じ）
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

    // UserData作成（Phase2-2の成功版 + Metabase）
    const userData = ec2.UserData.forLinux();
    userData.addCommands(
      'set -e',
      'yum update -y',
      
      // Docker インストール
      'yum install -y docker',
      'systemctl start docker',
      'systemctl enable docker',
      'usermod -a -G docker ec2-user',
      
      // Metabase起動
      'docker run -d --name metabase -p 3000:3000 --restart unless-stopped metabase/metabase',
      
      'echo "UserData completed successfully" > /tmp/userdata-complete.txt',
    );

    // IAMロール作成
    const role = new iam.Role(this, 'EC2Role', { 
      assumedBy: new iam.ServicePrincipal('ec2.amazonaws.com'),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName('AmazonSSMManagedInstanceCore'),
      ],
    });

    // EC2インスタンス（Phase1と同じt2.micro）
    const instance = new ec2.Instance(this, 'BaseballEC2', {
      vpc,
      vpcSubnets: {
        subnetType: ec2.SubnetType.PUBLIC,
      },
      instanceType: ec2.InstanceType.of(
        ec2.InstanceClass.T2,  // T3 → T2に変更
        ec2.InstanceSize.MICRO,
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
  }
}