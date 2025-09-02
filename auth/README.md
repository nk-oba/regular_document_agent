# Google OAuth2.0認証設定ガイド

このガイドでは、MCP ADAツールで401エラーを解決するためのGoogle OAuth2.0認証設定方法を説明します。

## 1. Google Cloud Console設定

### 1.1 プロジェクトの作成・選択
1. [Google Cloud Console](https://console.cloud.google.com) にアクセス
2. 新しいプロジェクトを作成するか、既存のプロジェクトを選択

### 1.2 必要なAPIの有効化
1. **APIとサービス** → **ライブラリ** に移動
2. 以下のAPIを検索して有効化：
   - Google Ads API
   - Google Analytics Reporting API (必要に応じて)

### 1.3 OAuth2.0認証情報の作成
1. **APIとサービス** → **認証情報** に移動
2. **認証情報を作成** → **OAuth クライアント ID** を選択
3. アプリケーションの種類: **デスクトップ アプリケーション**
4. 名前を入力 (例: "MCP ADA Tool")
5. **作成** をクリック

### 1.4 クライアントシークレットファイルのダウンロード
1. 作成した認証情報の **ダウンロード** アイコンをクリック
2. JSONファイルを `client_secrets.json` として保存

## 2. 環境設定

### 2.1 依存関係のインストール
```bash
cd agents
pip install -r requirements.txt
```

### 2.2 認証情報の配置
1. ダウンロードした `client_secrets.json` をプロジェクトルートに配置
2. 環境変数を設定：
```bash
export GOOGLE_OAUTH_CLIENT_SECRETS="$(pwd)/client_secrets.json"
```

## 3. 認証の実行

### 3.1 初回認証
```bash
python scripts/authenticate.py
```

### 3.2 認証プロセス
1. ブラウザが自動で開きます（手動でURLにアクセスも可能）
2. Googleアカウントでログイン
3. アプリケーションへのアクセス許可を承認
4. 表示された認証コードをコピー
5. ターミナルに認証コードを貼り付け

### 3.3 認証の更新
認証情報を更新する場合：
```bash
python scripts/authenticate.py --force
```

## 4. トラブルシューティング

### 4.1 よくあるエラー

**エラー**: `Client secrets file not found`
- **解決策**: `GOOGLE_OAUTH_CLIENT_SECRETS` 環境変数が正しく設定されているか確認

**エラー**: `OAuth flow failed`
- **解決策**: 
  - Google Cloud ConsoleでOAuth認証情報が正しく設定されているか確認
  - 必要なAPIが有効化されているか確認
  - リダイレクトURIが `http://localhost:8080` に設定されているか確認

**エラー**: `401 Unauthorized` (MCP ADAツールにて)
- **解決策**: 
  - `python scripts/authenticate.py` を実行して認証を完了
  - 認証情報が期限切れの場合は `--force` オプションで再認証

### 4.2 認証情報の確認
認証状態を確認：
```python
from auth.google_auth import get_google_access_token
token = get_google_access_token()
if token:
    print("認証成功")
else:
    print("認証が必要")
```

## 5. セキュリティ注意事項

- `client_secrets.json` をバージョン管理に含めないでください
- `google_credentials.json` (自動生成される認証情報) も機密情報です
- プロジェクト共有時は `.gitignore` に以下を追加：
```
client_secrets.json
google_credentials.json
```

## 6. ファイル構成
```
agents/
├── auth/
│   ├── google_auth.py          # 認証ロジック
│   └── README.md              # このファイル
├── scripts/
│   └── authenticate.py        # 認証実行スクリプト
├── client_secrets.json        # Google OAuth設定 (手動配置)
└── google_credentials.json    # 認証情報 (自動生成)
```