# Baseball CDK Project

## プロジェクト概要

このプロジェクトは、AWS CDKを使用して構築された野球データ収集・保存システムです。`pybaseball`ライブラリを使用してMLBの打撃統計データを取得し、PostgreSQL RDSに保存します。毎週日曜0時（UTC）にEventBridgeスケジューラーにより自動実行されます。

## アーキテクチャ

```
EventBridge (週次スケジュール)
    ↓
Lambda (ECRコンテナ, VPC外)
    ↓ (SSL接続)
RDS PostgreSQL (パブリックアクセス)
    ↓
CloudWatch Alarms
    ↓
SNS Topic
    ↓
Slack Notifier Lambda → Slack
```

### 主要な設計判断

- **Lambda VPC外配置**: pybaseballがインターネットアクセスを必要とするため、LambdaをVPC外に配置
- **RDS パブリックアクセス**: VPC外のLambdaから接続するため、SSL接続（`sslmode=require`）を必須化
- **コンテナイメージ**: pandas/numpy等の重い依存関係を含むため、Lambda Layer（250MB制限）ではなくECRコンテナイメージを使用
- **長時間実行**: データ取得に時間がかかるため、Lambda timeout = 15分、メモリ = 3008MB

## プロジェクト構造

```
.
├── bin/
│   └── baseball-cdk.js          # CDK appエントリーポイント
├── lib/
│   └── baseball-cdk-stack.ts    # メインCDKスタック定義
├── lambda/
│   ├── baseball_lambda.py       # データ取得Lambda関数
│   ├── Dockerfile               # Lambda用コンテナイメージ
│   ├── requirements.txt         # Python依存関係
│   └── slack-notifier/
│       └── index.py             # Slack通知Lambda
├── .env                         # 環境変数（gitignore済み）
├── cdk.json                     # CDK設定
└── package.json                 # Node.js依存関係
```

## データベーススキーマ

### `baseball_batting_historical` テーブル

| カラム名      | 型             | 説明                          |
|---------------|----------------|-------------------------------|
| id            | SERIAL         | 主キー                        |
| name          | VARCHAR(100)   | 選手名                        |
| season        | INTEGER        | シーズン年                    |
| games         | INTEGER        | 出場試合数                    |
| at_bats       | INTEGER        | 打数                          |
| runs          | INTEGER        | 得点                          |
| hits          | INTEGER        | 安打数                        |
| hr            | INTEGER        | ホームラン数                  |
| rbi           | INTEGER        | 打点                          |
| sb            | INTEGER        | 盗塁数                        |
| avg           | DECIMAL(5,3)   | 打率                          |
| created_at    | TIMESTAMP      | レコード作成日時              |

**ユニーク制約**: `(name, season)` - 同一選手の同一シーズンデータは上書き更新

## 環境変数

### .env ファイル（ルートディレクトリ）

```env
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

### Lambda環境変数（CDKが自動設定）

| 変数名             | 説明                              | デフォルト値        |
|--------------------|-----------------------------------|---------------------|
| DB_HOST            | RDSエンドポイント                 | CDKが自動設定       |
| DB_PORT            | RDSポート                         | CDKが自動設定       |
| DB_NAME            | データベース名                    | `postgres`          |
| DB_USER            | ユーザー名                        | `postgres`          |
| DB_PASSWORD        | パスワード                        | CDKが自動設定       |
| START_YEAR         | データ取得開始年                  | `2015`              |
| END_YEAR           | データ取得終了年                  | `2025`              |
| PYBASEBALL_CACHE   | pybaseballキャッシュディレクトリ  | `/tmp/.pybaseball`  |

## デプロイ手順

### 前提条件

- AWS CLI設定済み
- Node.js 18以上
- Docker Desktop起動中
- ECRリポジトリ `baseball-lambda` が作成済み

### 1. 環境変数設定

```bash
# .envファイルを作成してSLACK_WEBHOOK_URLを設定
echo "SLACK_WEBHOOK_URL=https://hooks.slack.com/services/XXX/YYY/ZZZ" > .env
```

### 2. CDK依存関係インストール

```bash
npm install
```

### 3. Dockerイメージビルド & ECRプッシュ

```bash
# ECRログイン
aws ecr get-login-password --region ap-northeast-1 | docker login --username AWS --password-stdin <ACCOUNT_ID>.dkr.ecr.ap-northeast-1.amazonaws.com

# イメージビルド
cd lambda
docker build -t baseball-lambda:v6 .

# タグ付け
docker tag baseball-lambda:v6 <ACCOUNT_ID>.dkr.ecr.ap-northeast-1.amazonaws.com/baseball-lambda:v6

# プッシュ
docker push <ACCOUNT_ID>.dkr.ecr.ap-northeast-1.amazonaws.com/baseball-lambda:v6
cd ..
```

### 4. CDKデプロイ

```bash
# 初回のみ
npx cdk bootstrap

# デプロイ
npx cdk deploy
```

### 5. 手動実行（テスト用）

```bash
aws lambda invoke \
  --function-name BaseballCdkStack-DataFetchFunctionV3XXX \
  --log-type Tail \
  response.json
```

## CloudWatch監視

以下のアラームが設定されています：

1. **Lambda-Errors**: Lambdaエラー発生時（閾値: 1回以上）
2. **Lambda-Timeout-Warning**: Lambda実行時間が14分以上
3. **Lambda-Throttles**: Lambda スロットリング発生時

すべてのアラームはSNS → Slack通知されます。

## トラブルシューティング

### pybaseballで2022年データが取得できない

**原因**: pybaseball 2.2.7の既知の制限
**対応**: `baseball_lambda.py:32`で`skip_years = [2022]`として自動スキップ

### Lambda タイムアウトエラー

**原因**: データ量が多い、またはpybaseballのAPI遅延
**対応**:
- `START_YEAR`/`END_YEAR`の範囲を狭める
- [lib/baseball-cdk-stack.ts:78](lib/baseball-cdk-stack.ts#L78) の`timeout`を延長（最大15分）

### RDS接続エラー "SSL connection required"

**原因**: SSL接続が無効
**対応**: [lambda/baseball_lambda.py:26](lambda/baseball_lambda.py#L26)で`sslmode: 'require'`が設定されているか確認

### Docker build時の依存関係エラー

**原因**: pyarrowのバイナリビルドに失敗
**対応**: [lambda/Dockerfile:5-7](lambda/Dockerfile#L5-L7)のフォールバック処理により自動的に`--no-deps`でpybaseballをインストール

### 特定の年だけデータ取得に失敗する

**症状**: ログに`✗ YYYY: FAILED`と表示される
**対応**:
- Lambdaログで詳細エラーを確認
- 当該年度がMLB開催年か確認（ストライキ等）
- 必要に応じて`skip_years`配列に追加

## よくある操作

### データ取得年度範囲の変更

[lib/baseball-cdk-stack.ts:86-87](lib/baseball-cdk-stack.ts#L86-L87)を編集:

```typescript
START_YEAR: '2015',  // 開始年
END_YEAR: '2025',    // 終了年（現在シーズン含む）
```

その後、`npx cdk deploy`で反映。

### スケジュール変更（週次 → 日次など）

[lib/baseball-cdk-stack.ts:170-174](lib/baseball-cdk-stack.ts#L170-L174)を編集:

```typescript
// 毎日0時に変更する場合
schedule: events.Schedule.cron({
  hour: '0',
  minute: '0',
}),
```

### ECRイメージバージョン更新

1. [lib/baseball-cdk-stack.ts:76](lib/baseball-cdk-stack.ts#L76)の`tagOrDigest`を変更:
   ```typescript
   { tagOrDigest: 'v7' }  // v6 → v7
   ```

2. 新しいイメージをビルド・プッシュ後、`npx cdk deploy`

### RDSインスタンスタイプ変更（コスト最適化）

[lib/baseball-cdk-stack.ts:55-58](lib/baseball-cdk-stack.ts#L55-L58):

```typescript
instanceType: ec2.InstanceType.of(
  ec2.InstanceClass.T3,     // T4G (ARM) に変更可能
  ec2.InstanceSize.MICRO,   // SMALL, MEDIUM等に変更可能
),
```

## セキュリティ考慮事項

- RDSパスワードはSecrets Managerで自動管理
- RDSはパブリックアクセス可だが、SSL接続必須
- セキュリティグループでRDSポート3306をインターネットに公開（要見直し: 特定IP制限推奨）
- `.env`ファイルは`.gitignore`で除外済み

## コスト概算（月額）

- RDS t3.micro（常時起動）: ~$15
- Lambda実行（週1回、15分）: ~$0.50
- CloudWatch Logs: ~$1
- ECR保存（1イメージ）: ~$0.10
- **合計**: ~$17/月

## GitHub Actions（CI/CD）

このプロジェクトではGitHub Actionsを使用してDockerイメージの自動ビルド・プッシュを実装しています。

### 自動ビルドワークフロー

**トリガー条件:**
- `main`ブランチへ`lambda/`配下の変更をpush
- 手動実行（Actions タブから）

**処理内容:**
1. Dockerイメージビルド（`--platform linux/amd64`）
2. バージョンタグ自動生成（コミット数ベース: v8, v9...）
3. ECRへプッシュ（バージョンタグ + `latest`）

**設定ファイル:** [.github/workflows/build-lambda.yml](.github/workflows/build-lambda.yml)

### セットアップ手順

1. **GitHub Secretsの設定**（リポジトリSettings → Secrets）
   - `AWS_ACCESS_KEY_ID`
   - `AWS_SECRET_ACCESS_KEY`

2. **IAM権限**: ECRプッシュ権限が必要
   ```json
   {
     "Action": [
       "ecr:GetAuthorizationToken",
       "ecr:BatchCheckLayerAvailability",
       "ecr:PutImage",
       "ecr:InitiateLayerUpload",
       "ecr:UploadLayerPart",
       "ecr:CompleteLayerUpload"
     ]
   }
   ```

3. **デプロイフロー**
   ```
   lambda/変更 → git push → Actions自動実行 → ECRプッシュ
   → 手動でtagOrDigest更新 → npx cdk deploy
   ```

詳細は [.github/README.md](.github/README.md) を参照。

## 今後の改善案

- [ ] RDSをプライベートサブネットに移動（LambdaをVPC内配置）
- [ ] データ差分取得（全件取得からの最適化）
- [ ] DynamoDBによる実行履歴管理
- [ ] Step Functionsによるリトライ処理
- [ ] インスタンスクラスをt4g（ARM）に変更してコスト削減
- [ ] RDS Proxyの導入
- [ ] GitHub ActionsでCDK自動デプロイ（テスト環境）
- [ ] PR時のCDK差分チェック
