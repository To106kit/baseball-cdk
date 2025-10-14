import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as rds from 'aws-cdk-lib/aws-rds';
import * as iam from 'aws-cdk-lib/aws-iam';

export class BaseballCdkStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // VPC作成
    const vpc = new ec2.Vpc(this, 'BaseballVPC', {
      maxAzs: 2,
      subnetConfiguration: [
        {
          name: 'Public',
          subnetType: ec2.SubnetType.PUBLIC,
        },
        {
          name: 'Isolated',
          subnetType: ec2.SubnetType.PRIVATE_ISOLATED,
        },
      ],
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

    // UserData作成
    const userData = ec2.UserData.forLinux();
    userData.addCommands(
      'set -e',
      'yum update -y',
      'systemctl start sshd',
      'systemctl enable sshd',
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