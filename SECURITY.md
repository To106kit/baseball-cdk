# セキュリティポリシー

## リポジトリ公開前チェックリスト

このリポジトリを公開する前に、以下のセキュリティチェックを完了しました：

### ✅ 完了項目

- [x] **AWS Account ID削除**: プレースホルダー `<ACCOUNT_ID>` に置き換え
- [x] **ハードコードされたパスワード削除**: `ec2/baseball_historical_import.py` を.gitignore追加
- [x] **機密設定ファイル除外**:
  - `phase1-config.json`
  - `cdk.context.json`
  - `metabase-policy.json`
- [x] **環境変数**: `.env` ファイルが.gitignore済み
- [x] **Slack Webhook**: 環境変数経由で管理、ハードコード無し
- [x] **AWS認証情報**: GitHub Secretsで管理、コードには未含有

### 🔒 保護されている機密情報

以下の情報は`.gitignore`により保護されています：

```
.env                              # 環境変数（SLACK_WEBHOOK_URL等）
cdk.context.json                  # AWS Account ID含む
phase1-config.json                # EC2設定（Account ID含む）
ec2/baseball_historical_import.py  # RDSパスワード含む
metabase-policy.json              # Account ID含むIAMポリシー
response.json                     # Lambdaテスト結果
cdk.out/                          # CDK生成ファイル
```

### 📝 公開リポジトリで必要な設定

このリポジトリをクローンして使用する場合、以下の設定が必要です：

#### 1. 環境変数ファイル (.env)

```bash
# .envファイルを作成
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

#### 2. AWS認証情報

```bash
# AWS CLIで認証設定
aws configure

# または環境変数
export AWS_ACCESS_KEY_ID=<your-access-key>
export AWS_SECRET_ACCESS_KEY=<your-secret-key>
export AWS_DEFAULT_REGION=ap-northeast-1
```

#### 3. GitHub Secrets（GitHub Actions使用時）

リポジトリSettings → Secrets and variables → Actionsで設定:
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`

#### 4. Metabase IAM User

```bash
# IAMユーザー作成
aws iam create-user --user-name metabase-athena-user

# ポリシーをアタッチ（metabase-policy.jsonのサンプルを参考）
aws iam put-user-policy --user-name metabase-athena-user \
  --policy-name MetabaseAthenaAccess \
  --policy-document file://metabase-policy.json.example

# アクセスキー生成
aws iam create-access-key --user-name metabase-athena-user
```

## 脆弱性報告

セキュリティ上の問題を発見した場合:
- **公開Issue報告は避けてください**
- GitHubのSecurity Advisoriesを使用
- または直接メール: [セキュリティ担当者のメールアドレス]

## サポート対象バージョン

| バージョン | サポート状況 |
| ------- | ------- |
| main    | ✅ サポート中 |
| その他   | ❌ サポート終了 |

## 既知の制限事項

### RDSからの移行履歴

このプロジェクトは元々RDS PostgreSQLを使用していましたが、S3 Data Lakeに移行しました。
- RDS関連コード（`ec2/`ディレクトリ）はレガシーとして残していますが、現在は使用していません
- これらのファイルには機密情報が含まれるため、`.gitignore`で除外しています

### Athenaクエリコスト

Athenaは従量課金制です：
- $5.00 per TB（スキャンしたデータ量）
- 現在のデータ量: 205KB（ほぼ無料）
- 月間100回クエリでも約$0.005（0.5円）

## 推奨セキュリティプラクティス

1. **最小権限の原則**: IAMロールには必要最小限の権限のみ付与
2. **環境変数の使用**: 認証情報は環境変数で管理
3. **定期的なキーローテーション**: 3ヶ月ごとにアクセスキーを更新
4. **CloudWatch Alarms**: エラー/タイムアウト/スロットリングを監視
5. **S3バケット暗号化**: SSE-S3による自動暗号化
6. **S3 Block Public Access**: 全てのパブリックアクセスをブロック

## ライセンス

[LICENSE](LICENSE)を参照してください。
