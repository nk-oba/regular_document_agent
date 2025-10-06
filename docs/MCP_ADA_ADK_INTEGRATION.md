# MCP ADA with Google ADK Authentication Integration

## 概要

このドキュメントは、MCP ADA (Ad Analyzer) をGoogle ADK標準の認証方式で統合する実装について説明します。

## アーキテクチャ

### 1. 認証コンポーネント

#### **mcp_ada_adk_auth.py**
ADK標準の`AuthCredential`と`AuthScheme`を使用したMCP ADA認証の定義。

**主要な機能:**
- `create_mcp_ada_auth_scheme()`: OAuth2認証スキームの作成
- `create_mcp_ada_auth_credential(user_id)`: ユーザー固有の認証資格情報の作成
- `get_mcp_ada_token_from_state(state)`: ADKセッションからトークンを取得
- `is_mcp_ada_authenticated(state)`: 認証状態の確認

#### **credential_manager.py**
ADKの`SessionService`を使用したトークン管理。

**主要な機能:**
- `store_tokens()`: OAuth2トークンをADKセッションに保存
- `get_access_token()`: アクセストークンの取得
- `get_refresh_token()`: リフレッシュトークンの取得
- `clear_tokens()`: トークンのクリア
- `is_authenticated()`: 認証状態の確認

### 2. 認証フロー

```
┌──────────┐         ┌──────────┐         ┌───────────┐         ┌──────────┐
│  User    │         │  Agent   │         │ MCP ADA   │         │   ADK    │
│          │         │  Tool    │         │  Server   │         │ Session  │
└────┬─────┘         └────┬─────┘         └─────┬─────┘         └────┬─────┘
     │                    │                     │                     │
     │  1. Call Tool      │                     │                     │
     ├───────────────────>│                     │                     │
     │                    │                     │                     │
     │                    │  2. Check Token     │                     │
     │                    ├────────────────────────────────────────────>│
     │                    │<─────────────────────────────────────────────┤
     │                    │  (No token found)   │                     │
     │                    │                     │                     │
     │                    │  3. Request Credential                    │
     │                    │     (tool_context.request_credential)     │
     │<───────────────────┤                     │                     │
     │  Auth Required     │                     │                     │
     │                    │                     │                     │
     │  4. Start OAuth2   │                     │                     │
     ├────────────────────┼─────────────────────>│                     │
     │                    │                     │                     │
     │  5. Authorization  │                     │                     │
     │<────────────────────────────────────────┤                     │
     │                    │                     │                     │
     │  6. Callback with  │                     │                     │
     │     Auth Code      │                     │                     │
     ├────────────────────>│                     │                     │
     │                    │                     │                     │
     │                    │  7. Exchange Token  │                     │
     │                    ├─────────────────────>│                     │
     │                    │<─────────────────────┤                     │
     │                    │  (Access Token)      │                     │
     │                    │                     │                     │
     │                    │  8. Store in Session │                     │
     │                    ├────────────────────────────────────────────>│
     │                    │                     │                     │
     │  9. Tool Retry     │                     │                     │
     ├───────────────────>│                     │                     │
     │                    │                     │                     │
     │                    │  10. Get Token      │                     │
     │                    ├────────────────────────────────────────────>│
     │                    │<─────────────────────────────────────────────┤
     │                    │  (Token found)      │                     │
     │                    │                     │                     │
     │                    │  11. Call MCP API   │                     │
     │                    ├─────────────────────>│                     │
     │                    │<─────────────────────┤                     │
     │                    │  (API Response)      │                     │
     │                    │                     │                     │
     │  12. Return Result │                     │                     │
     │<───────────────────┤                     │                     │
```

## 実装例

### ツールでの使用方法

```python
from google.adk import ToolContext
from google.adk.auth import AuthConfig
from shared.auth.mcp_ada_adk_auth import (
    create_mcp_ada_auth_scheme,
    create_mcp_ada_auth_credential,
    get_mcp_ada_token_from_state
)

def mcp_ada_get_report(
    tool_context: ToolContext,
    property_id: str,
    start_date: str,
    end_date: str
):
    """MCP ADAからレポートを取得"""

    # セッションからトークンを確認
    cached_token = get_mcp_ada_token_from_state(tool_context.state)

    if not cached_token:
        # 認証が必要な場合、ADKに認証をリクエスト
        auth_scheme = create_mcp_ada_auth_scheme()
        auth_credential = create_mcp_ada_auth_credential(tool_context.user_id)

        tool_context.request_credential(AuthConfig(
            auth_scheme=auth_scheme,
            raw_auth_credential=auth_credential
        ))

        return {
            'pending': True,
            'message': 'Authentication required'
        }

    # 認証済み - MCP ADA APIを呼び出し
    from mcp_client.mcp_toolset import MCPToolset
    from mcp_client.transport.http_client import StreamableHTTPConnectionParams

    toolset = MCPToolset(
        connection_params=StreamableHTTPConnectionParams(
            url="https://mcp-server-ad-analyzer.adt-c1a.workers.dev/mcp",
            headers={"Authorization": f"Bearer {cached_token}"}
        )
    )

    result = toolset.call_tool("get_ad_report", {
        "property_id": property_id,
        "start_date": start_date,
        "end_date": end_date
    })

    return {'success': True, 'data': result}
```

### コールバックエンドポイント

```python
@app.post("/auth/mcp-ada/callback")
async def mcp_ada_callback(request: dict, fastapi_request: Request):
    """MCP ADA認証コールバック"""

    # 認証コードを処理
    credentials = auth_manager.process_auth_code(
        request.get('code'),
        request.get('state')
    )

    # ADKセッションにトークンを保存
    session_id = fastapi_request.cookies.get("adk_session_id")

    if session_id and credentials:
        credential_manager = MCPADACredentialManager(session_service)
        await credential_manager.store_tokens(
            session_id=session_id,
            access_token=credentials['access_token'],
            refresh_token=credentials.get('refresh_token')
        )

    return {"success": True, "authenticated": True}
```

## 設定

### 環境変数

```bash
# MCP ADAリダイレクトURI（本番環境では必須）
MCP_ADA_REDIRECT_URI=https://your-domain.com/static/mcp_ada_callback.html
```

### 本番環境デプロイ時の注意事項

1. **リダイレクトURIの設定**
   - 開発環境: `http://localhost:8000/static/mcp_ada_callback.html`
   - 本番環境: `https://your-domain.com/static/mcp_ada_callback.html`

2. **セキュリティ**
   - トークンはADK SessionServiceに安全に保存されます
   - リフレッシュトークンも暗号化して保存
   - セッションタイムアウト設定を適切に設定

3. **エラーハンドリング**
   - トークン期限切れ時は自動的に再認証をリクエスト
   - ネットワークエラーは適切にログに記録

## ファイル構成

```
agents/
├── shared/
│   ├── auth/
│   │   ├── mcp_ada_auth.py              # 既存のMCP ADA認証（ファイルベース）
│   │   └── mcp_ada_adk_auth.py          # NEW: ADK標準認証コンポーネント
│   └── services/
│       └── credential_manager.py         # NEW: ADKセッションベースのトークン管理
├── ai_agents/
│   └── document_creating_agent/
│       ├── tools.py                      # 既存のツール
│       └── mcp_ada_tools_adk.py          # NEW: ADK標準認証を使用したツール例
├── api/
│   └── main.py                           # 更新: コールバックエンドポイント
└── docs/
    └── MCP_ADA_ADK_INTEGRATION.md        # このドキュメント
```

## テスト

### 認証フローのテスト

1. ユーザーがツールを呼び出す
2. 認証が必要な場合、フロントエンドに認証リクエストが返される
3. ユーザーがMCP ADA OAuth2フローを完了
4. トークンがADKセッションに保存される
5. ツールが再実行され、APIコールが成功する

### 単体テスト例

```python
import pytest
from shared.auth.mcp_ada_adk_auth import create_mcp_ada_auth_scheme

def test_create_auth_scheme():
    scheme = create_mcp_ada_auth_scheme()
    assert scheme.authorization_endpoint.startswith("https://")
    assert "mcp:reports" in scheme.scopes
```

## 今後の拡張

1. **トークンリフレッシュの自動化**
   - トークン期限切れ時に自動でリフレッシュ

2. **複数MCPサーバーのサポート**
   - 他のMCPサーバー（PowerPoint等）にも同じパターンを適用

3. **監視とログ**
   - 認証エラーのメトリクス収集
   - トークン使用状況の追跡

## トラブルシューティング

### 認証が繰り返し要求される

- ADKセッションIDが正しく渡されているか確認
- SessionServiceがapp.stateに設定されているか確認
- トークンの有効期限を確認

### トークンが見つからない

- ブラウザのクッキーが有効か確認
- セッションがタイムアウトしていないか確認

## 参考リンク

- [Google ADK Authentication Documentation](https://google.github.io/adk-docs/tools/authentication/)
- [MCP ADA Server Documentation](https://mcp-server-ad-analyzer.adt-c1a.workers.dev/)
