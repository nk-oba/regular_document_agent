# MCP Client Authentication Framework

MCP ADA準拠のOAuth 2.1認証フレームワーク

## 概要

このフレームワークは、Model Context Protocol (MCP) Authorization and Authentication (ADA) 仕様に完全準拠したクライアント認証ライブラリです。OAuth 2.1 + PKCE、動的クライアント登録、自動HTTP 401処理を提供します。

## 主要機能

### 🔐 セキュリティファースト
- **OAuth 2.1準拠**: 最新のセキュリティ標準
- **PKCE必須**: S256チャレンジメソッド
- **暗号化ストレージ**: 全トークンの暗号化保存
- **状態検証**: CSRF攻撃防止

### 🚀 自動化機能  
- **動的クライアント登録**: 初回接続時の自動登録
- **サーバー発見**: `.well-known/oauth-protected-resource`エンドポイント
- **HTTP 401自動処理**: 認証切れの自動検出・処理
- **トークン自動更新**: リフレッシュトークンによる更新

### 🎯 使いやすさ
- **シンプルAPI**: 直感的なインターフェース
- **マルチユーザー対応**: ユーザー毎の独立認証状態
- **エラーハンドリング**: 包括的なエラー処理
- **設定駆動**: 環境変数による柔軟な設定

## インストール

```bash
pip install cryptography httpx pydantic
```

## 基本的な使用方法

### シンプルな認証クライアント

```python
import asyncio
from agents.mcp_client import MCPAuthClient

async def main():
    async with MCPAuthClient("https://mcp-server.example.com") as client:
        # 認証が必要な場合は自動的に処理される
        response = await client.make_authenticated_request("GET", "/api/data")
        print(response.json())

asyncio.run(main())
```

### 認証コールバック付き

```python
from agents.mcp_client.transport.http_client import SimpleAuthenticatedClient

def handle_auth(auth_url: str):
    """認証URLが提供された時の処理"""
    print(f"Please authenticate at: {auth_url}")
    # ブラウザを開く、QRコードを表示するなど

async def main():
    async with SimpleAuthenticatedClient(
        "https://mcp-server.example.com",
        auth_callback=handle_auth
    ) as client:
        response = await client.get("/api/resources")
        print(response.json())
```

### ファクトリーパターン

```python
from agents.mcp_client.integration import MCPClientFactory

# HTTPクライアントを作成
http_client = MCPClientFactory.create_http_client(
    "https://mcp-server.example.com",
    user_id="user123",
    auth_callback=handle_auth
)

async with http_client.auth_client:
    response = await http_client.get("/api/data")
```

## 高度な設定

### カスタム設定

```python
from agents.mcp_client.config.settings import MCPClientConfig, ServerConfig

# グローバル設定
config = MCPClientConfig(
    timeout=60,
    max_retries=5,
    token_cache_ttl=600,
    require_https=True
)

# サーバー固有設定
server_config = ServerConfig(
    url="https://mcp-server.example.com",
    name="My MCP Server",
    scopes=['read', 'write', 'admin'],
    redirect_uri='http://localhost:8080/callback'
)
config.add_server(server_config)

# 設定を使用してクライアント作成
client = MCPAuthClient("https://mcp-server.example.com", config=config)
```

### 環境変数設定

```bash
# 暗号化パスワード（推奨）
export MCP_CLIENT_CRYPTO_PASSWORD="your-secure-password"

# HTTP設定
export MCP_CLIENT_TIMEOUT=60
export MCP_CLIENT_REQUIRE_HTTPS=true

# ログ設定
export MCP_CLIENT_LOG_LEVEL=DEBUG
```

## Webアプリケーション統合

### FastAPI統合

```python
from fastapi import FastAPI, Depends
from agents.mcp_client.integration import WebIntegration

app = FastAPI()

# 認証依存関数を作成
auth_dependency = WebIntegration.create_fastapi_auth_dependency(
    "https://mcp-server.example.com"
)

@app.get("/protected")
async def protected_endpoint(token: str = Depends(auth_dependency)):
    # 認証済みのエンドポイント
    return {"message": "Authenticated!", "token": token}
```

### Flask統合

```python
from flask import Flask
from agents.mcp_client.integration import WebIntegration

app = Flask(__name__)

# 認証デコレータを作成
require_auth = WebIntegration.create_flask_auth_decorator(
    "https://mcp-server.example.com"
)

@app.route("/protected")
@require_auth
def protected_endpoint():
    return {"message": "Authenticated!"}
```

## CLI統合

### Click統合

```python
import click
from agents.mcp_client.integration import CLIIntegration

@click.group()
def cli():
    pass

# 認証コマンドを追加
auth_command = CLIIntegration.create_click_auth_command(
    "https://mcp-server.example.com"
)
cli.add_command(auth_command, name="authenticate")

if __name__ == '__main__':
    cli()
```

## エラーハンドリング

### エラーハンドリングデコレータ

```python
from agents.mcp_client.error_handler import with_error_handling

@with_error_handling()
async def my_api_call():
    async with MCPAuthClient("https://mcp-server.example.com") as client:
        return await client.make_authenticated_request("GET", "/api/data")

# エラーは自動的に処理される
result = await my_api_call()
```

### カスタムエラーハンドラー

```python
from agents.mcp_client.error_handler import ErrorHandler
from agents.mcp_client.auth.exceptions import TokenExpiredError

def custom_token_handler(error, context):
    print(f"Token expired for {context.get('server_url')}")
    return "token_refresh_needed"

error_handler = ErrorHandler()
error_handler.register_error_handler(TokenExpiredError, custom_token_handler)
```

## レガシーシステム移行

### 既存トークンの移行

```python
from agents.mcp_client.integration import LegacyIntegration

# 既存の認証情報を移行
success = LegacyIntegration.migrate_existing_tokens(
    old_credentials_file="/path/to/old_credentials.json",
    server_url="https://mcp-server.example.com",
    user_id="user123"
)

if success:
    print("Migration completed successfully!")
```

## テスト

### ユニットテスト実行

```bash
# 全テスト実行
python -m pytest agents/tests/mcp_client/

# 特定のテスト実行
python -m pytest agents/tests/mcp_client/test_pkce_handler.py

# カバレッジ付き実行
python -m pytest --cov=agents.mcp_client agents/tests/mcp_client/
```

### モックを使用したテスト

```python
import pytest
from unittest.mock import AsyncMock, patch
from agents.mcp_client import MCPAuthClient

@pytest.mark.asyncio
async def test_api_call():
    with patch('httpx.AsyncClient') as mock_client:
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": "test"}
        
        mock_client.return_value.__aenter__.return_value.request.return_value = mock_response
        
        async with MCPAuthClient("https://test.com") as client:
            response = await client.make_authenticated_request("GET", "/api/test")
            assert response.status_code == 200
```

## 設定オプション

### MCPClientConfig

| オプション | デフォルト | 説明 |
|-----------|------------|------|
| `timeout` | 30 | HTTPタイムアウト（秒） |
| `max_retries` | 3 | 最大リトライ回数 |
| `token_cache_ttl` | 300 | トークンキャッシュ有効時間（秒） |
| `require_https` | True | HTTPS必須 |
| `validate_ssl` | True | SSL証明書検証 |

### ServerConfig

| オプション | 説明 |
|-----------|------|
| `url` | サーバーURL（必須） |
| `name` | サーバー名 |
| `scopes` | 要求するスコープ |
| `redirect_uri` | リダイレクトURI |
| `client_name` | クライアント名 |

## トラブルシューティング

### よくある問題

**1. 認証が失敗する**
```python
# デバッグログを有効化
import logging
logging.basicConfig(level=logging.DEBUG)
```

**2. SSL証明書エラー**
```python
config = MCPClientConfig(validate_ssl=False)  # 開発環境のみ
```

**3. タイムアウトエラー**
```python
config = MCPClientConfig(timeout=120)  # 2分に延長
```

## セキュリティ考慮事項

1. **暗号化パスワード**: `MCP_CLIENT_CRYPTO_PASSWORD`環境変数を必ず設定
2. **HTTPS必須**: 本番環境では`require_https=True`を維持
3. **リダイレクトURI**: 信頼できるURIのみ使用
4. **トークン管理**: トークンをログ出力しない
5. **権限管理**: 最小限のスコープのみ要求

## ライセンス

MIT License

## 貢献

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)  
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## サポート

- Issues: [GitHub Issues](https://github.com/your-org/mcp-client/issues)
- Documentation: [Wiki](https://github.com/your-org/mcp-client/wiki)
- Discussions: [GitHub Discussions](https://github.com/your-org/mcp-client/discussions)