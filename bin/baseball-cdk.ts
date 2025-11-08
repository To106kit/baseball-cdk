#!/usr/bin/env node
import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import { BaseballCdkStack } from '../lib/baseball-cdk-stack';

const app = new cdk.App();

// 1つのスタックに統合
new BaseballCdkStack(app, 'BaseballCdkStack', {
  env: { 
    account: process.env.CDK_DEFAULT_ACCOUNT, 
    region: process.env.CDK_DEFAULT_REGION 
  },
});