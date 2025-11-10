# ⚾ Baseball Stats Data Lake

AWS CDKを使用して構築されたMLB野球統計データ収集・分析システムです。pybaseballライブラリでデータを取得し、S3 Data LakeにParquet形式で保存します。

![Architecture Diagram](baseball-cdk-architecture.png)

## 主な特徴

- 📊 **S3 Data Lake**: Parquet形式で年度別パーティション保存
- 🔍 **Amazon Athena**: SQLでサーバーレスクエリ
- 📈 **コスト効率**: 月額 $0.85（RDSから95%削減）
- 🤖 **完全自動化**: 週次でEventBridgeスケジューラー実行
- 🔔 **Slack通知**: エラー/タイムアウト時に自動通知
- 🎨 **アーキテクチャ図自動生成**: インフラ変更時に自動更新

## アーキテクチャ

```
EventBridge → Lambda (ECR) → S3 Data Lake → Glue → Athena → Metabase
                   ↓
           CloudWatch Alarms → SNS → Slack
```

詳細は [CLAUDE.md](CLAUDE.md) を参照してください。

## クイックスタート

### 前提条件

- Node.js 18+
- AWS CLI設定済み
- Docker Desktop
- Python 3.12

### 1. リポジトリクローン

```bash
git clone https://github.com/<your-username>/baseball-cdk.git
cd baseball-cdk
```

### 2. 依存関係インストール

```bash
npm install
```

### 3. 環境変数設定

```bash
# .envファイルを作成
echo "SLACK_WEBHOOK_URL=https://hooks.slack.com/services/XXX/YYY/ZZZ" > .env
```

### 4. ECRリポジトリ作成

```bash
aws ecr create-repository --repository-name baseball-lambda --region ap-northeast-1
```

### 5. Dockerイメージビルド & プッシュ

```bash
# ECRログイン
aws ecr get-login-password --region ap-northeast-1 | \
  docker login --username AWS --password-stdin <ACCOUNT_ID>.dkr.ecr.ap-northeast-1.amazonaws.com

# イメージビルド
cd lambda
docker build -t baseball-lambda:v1 .
docker tag baseball-lambda:v1 <ACCOUNT_ID>.dkr.ecr.ap-northeast-1.amazonaws.com/baseball-lambda:v1
docker push <ACCOUNT_ID>.dkr.ecr.ap-northeast-1.amazonaws.com/baseball-lambda:v1
cd ..
```

### 6. CDKデプロイ

```bash
# 初回のみ
npx cdk bootstrap

# デプロイ（アーキテクチャ図も自動生成）
npm run deploy
```

## 使用方法

### アーキテクチャ図の生成

```bash
# 図のみ生成
npm run diagram

# 図生成 + デプロイ
npm run deploy
```

### Athenaクエリ例

```sql
-- 2025年ホームラン王トップ10
SELECT name, hr, avg, games
FROM baseball_stats.batting_stats
WHERE year = 2025
ORDER BY hr DESC
LIMIT 10;
```

### Lambda手動実行

```bash
aws lambda invoke \
  --function-name BaseballCdkStack-DataFetchFunctionV3XXX \
  --log-type Tail \
  response.json
```

## プロジェクト構造

```
.
├── bin/
│   └── baseball-cdk.js          # CDK appエントリーポイント
├── lib/
│   └── baseball-cdk-stack.ts    # メインCDKスタック
├── lambda/
│   ├── baseball_lambda.py       # データ取得Lambda
│   ├── Dockerfile               # Lambda用コンテナイメージ
│   └── slack-notifier/          # Slack通知Lambda
├── .github/workflows/
│   ├── build-lambda.yml         # Dockerイメージ自動ビルド
│   ├── auto-create-pr.yml       # PR自動作成
│   └── generate-diagram.yml     # アーキテクチャ図自動生成
├── generate_architecture_diagram.py  # 図生成スクリプト
└── CLAUDE.md                    # 詳細ドキュメント
```

## コスト

| サービス | 月額 |
|----------|------|
| S3 (205KB) | $0.02 |
| Lambda実行 (週1回) | $0.50 |
| CloudWatch Logs | $0.05 |
| ECR | $0.10 |
| Athena (月10回) | $0.05 |
| Glue Data Catalog | 無料 |
| **合計** | **$0.85/月** |

## セキュリティ

セキュリティポリシーは [SECURITY.md](SECURITY.md) を参照してください。

主なセキュリティ対策：
- S3 Block Public Access有効
- SSE-S3による暗号化
- IAM最小権限の原則
- 環境変数による認証情報管理

## ライセンス

このプロジェクトはMITライセンスの下で公開されています。詳細は[LICENSE](LICENSE)ファイルを参照してください。

## 貢献

プルリクエストを歓迎します！大きな変更の場合は、まずIssueを開いて変更内容を議論してください。

## 詳細ドキュメント

- [CLAUDE.md](CLAUDE.md) - 詳細な技術ドキュメント
- [SECURITY.md](SECURITY.md) - セキュリティポリシー
- [.github/README.md](.github/README.md) - GitHub Actions CI/CD

## AI支援開発

このプロジェクトは以下のAIツールで開発されています：
- **Claude Code** - インフラストラクチャ設計・実装
- **CodeRabbit** - 自動コードレビュー

---

**Note**: このプロジェクトは個人学習用です。

