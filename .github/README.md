# GitHub Actions ワークフロー

このプロジェクトで使用しているGitHub Actionsワークフローのドキュメント。

## ワークフロー一覧

### 1. Lambda Image Build & Push

**ファイル**: [build-lambda.yml](workflows/build-lambda.yml)

**トリガー条件:**
- `main`ブランチへの`lambda/`配下の変更push時
- 手動実行（Actions タブから）

**処理内容:**
1. Lambda関数のDockerイメージをビルド
2. コミット数から自動的にバージョンタグ生成（v8, v9...）
3. ECRにプッシュ（バージョンタグ + `latest`タグ）

**出力:**
- ECRイメージ: `<ACCOUNT_ID>.dkr.ecr.ap-northeast-1.amazonaws.com/baseball-lambda:vX`
- ECRイメージ: `<ACCOUNT_ID>.dkr.ecr.ap-northeast-1.amazonaws.com/baseball-lambda:latest`

## セットアップ手順

### 1. GitHub Secretsの設定

リポジトリの **Settings → Secrets and variables → Actions** で以下を設定:

| Secret名 | 説明 | 取得方法 |
|----------|------|----------|
| `AWS_ACCESS_KEY_ID` | AWSアクセスキーID | IAMユーザーから取得 |
| `AWS_SECRET_ACCESS_KEY` | AWSシークレットキー | IAMユーザーから取得 |

**IAM権限要件:**
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ecr:GetAuthorizationToken",
        "ecr:BatchCheckLayerAvailability",
        "ecr:PutImage",
        "ecr:InitiateLayerUpload",
        "ecr:UploadLayerPart",
        "ecr:CompleteLayerUpload"
      ],
      "Resource": "*"
    }
  ]
}
```

### 2. ワークフローの実行確認

1. GitHubリポジトリの **Actions** タブを開く
2. ワークフロー一覧から **Build & Push Lambda Image** を選択
3. 実行履歴と結果を確認

### 3. 手動実行方法

1. **Actions** タブ → **Build & Push Lambda Image**
2. **Run workflow** ボタンをクリック
3. ブランチ選択して **Run workflow**

## デプロイフロー（自動化後）

```
┌─────────────────┐
│ lambda/配下を   │
│ 変更してコミット │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ mainブランチに  │
│ push/merge      │
└────────┬────────┘
         │
         ▼
┌─────────────────────────┐
│ GitHub Actions 自動起動 │
│ - Dockerビルド          │
│ - ECRプッシュ (v8, v9...) │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│ 手動でCDKスタック更新   │
│ 1. tagOrDigest: 'vX'    │
│ 2. npx cdk deploy       │
└─────────────────────────┘
```

## トラブルシューティング

### ワークフローが失敗する

**症状**: Actions タブで赤色のエラーアイコン

**確認項目:**
1. GitHub Secretsが正しく設定されているか
2. IAMユーザーにECR権限があるか
3. ログを確認してエラー内容を特定

### ECRにプッシュできない

**エラー例**: `denied: User is not authorized`

**対処法:**
- IAMユーザーにECR関連権限を付与
- アクセスキーが有効か確認

### バージョンタグが重複する

**原因**: コミット履歴が変更された（rebase等）

**対処法:**
- `BASE_VERSION`を手動で増やす（[build-lambda.yml](workflows/build-lambda.yml) Line 32）

## 今後の拡張案

- [ ] CDK差分チェック（PR時）
- [ ] 自動デプロイ（テスト環境）
- [ ] Slack通知（ビルド完了時）
- [ ] ドキュメントリンクチェック
