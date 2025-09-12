"""
MCP Server Implementation
MCP認証フレームワークをMCPツールとして提供するサーバー実装
"""

import asyncio
import json
import logging
from typing import Dict, Any, Optional, List, Union

import mcp.types as types
from mcp.server.models import InitializationOptions
from mcp.server import NotificationOptions, Server
from mcp.server.stdio import stdio_server

from .auth.client import MCPAuthClient
from .transport.http_client import AuthenticatedHTTPClient, SimpleAuthenticatedClient
from .integration import MCPClientFactory
from .config.settings import MCPClientConfig, ServerConfig
from .error_handler import handle_mcp_error

# ログ設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp-auth-server")

# サーバーインスタンス
server = Server("mcp-auth-client")

# グローバル状態管理
_auth_clients: Dict[str, MCPAuthClient] = {}
_configurations: Dict[str, MCPClientConfig] = {}


# ==============================================================================
# MCP Server Setup
# ==============================================================================

@server.list_tools()
async def handle_list_tools() -> List[types.Tool]:
    """
    利用可能なツールの一覧を返す
    """
    return [
        types.Tool(
            name="authenticate_mcp_server",
            description="MCP ADA準拠のOAuth 2.1認証を実行",
            inputSchema={
                "type": "object",
                "properties": {
                    "server_url": {
                        "type": "string",
                        "description": "MCPサーバーのURL"
                    },
                    "user_id": {
                        "type": "string",
                        "description": "ユーザーID（オプション）",
                        "default": "default"
                    },
                    "scopes": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "要求するスコープ",
                        "default": ["read", "write"]
                    }
                },
                "required": ["server_url"]
            }
        ),
        types.Tool(
            name="make_authenticated_request",
            description="認証付きHTTPリクエストを実行",
            inputSchema={
                "type": "object",
                "properties": {
                    "server_url": {
                        "type": "string",
                        "description": "MCPサーバーのURL"
                    },
                    "method": {
                        "type": "string",
                        "description": "HTTPメソッド",
                        "enum": ["GET", "POST", "PUT", "DELETE", "PATCH"]
                    },
                    "path": {
                        "type": "string",
                        "description": "リクエストパス"
                    },
                    "user_id": {
                        "type": "string",
                        "description": "ユーザーID",
                        "default": "default"
                    },
                    "headers": {
                        "type": "object",
                        "description": "追加のHTTPヘッダー",
                        "default": {}
                    },
                    "json_data": {
                        "type": "object",
                        "description": "JSONボディデータ"
                    },
                    "query_params": {
                        "type": "object",
                        "description": "クエリパラメータ",
                        "default": {}
                    }
                },
                "required": ["server_url", "method", "path"]
            }
        ),
        types.Tool(
            name="check_auth_status",
            description="認証状態を確認",
            inputSchema={
                "type": "object",
                "properties": {
                    "server_url": {
                        "type": "string",
                        "description": "MCPサーバーのURL"
                    },
                    "user_id": {
                        "type": "string",
                        "description": "ユーザーID",
                        "default": "default"
                    }
                },
                "required": ["server_url"]
            }
        ),
        types.Tool(
            name="revoke_authentication",
            description="認証を取り消し",
            inputSchema={
                "type": "object",
                "properties": {
                    "server_url": {
                        "type": "string",
                        "description": "MCPサーバーのURL"
                    },
                    "user_id": {
                        "type": "string",
                        "description": "ユーザーID",
                        "default": "default"
                    }
                },
                "required": ["server_url"]
            }
        ),
        types.Tool(
            name="configure_mcp_client",
            description="MCPクライアント設定を行う",
            inputSchema={
                "type": "object",
                "properties": {
                    "server_url": {
                        "type": "string",
                        "description": "MCPサーバーのURL"
                    },
                    "config": {
                        "type": "object",
                        "description": "クライアント設定",
                        "properties": {
                            "timeout": {"type": "integer", "default": 30},
                            "max_retries": {"type": "integer", "default": 3},
                            "require_https": {"type": "boolean", "default": True},
                            "scopes": {
                                "type": "array",
                                "items": {"type": "string"},
                                "default": ["read", "write"]
                            },
                            "redirect_uri": {"type": "string"}
                        }
                    }
                },
                "required": ["server_url", "config"]
            }
        ),
        types.Tool(
            name="list_configured_servers",
            description="設定済みサーバーの一覧を取得",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        )
    ]


@server.call_tool()
async def handle_call_tool(name: str, arguments: Dict[str, Any]) -> List[types.TextContent]:
    """
    ツール呼び出しを処理
    """
    try:
        if name == "authenticate_mcp_server":
            result = await _authenticate_mcp_server(**arguments)
        elif name == "make_authenticated_request":
            result = await _make_authenticated_request(**arguments)
        elif name == "check_auth_status":
            result = await _check_auth_status(**arguments)
        elif name == "revoke_authentication":
            result = await _revoke_authentication(**arguments)
        elif name == "configure_mcp_client":
            result = await _configure_mcp_client(**arguments)
        elif name == "list_configured_servers":
            result = await _list_configured_servers()
        else:
            raise ValueError(f"Unknown tool: {name}")
        
        return [types.TextContent(type="text", text=result)]
        
    except Exception as e:
        logger.error(f"Tool call failed: {e}")
        error_result = handle_mcp_error(e, {"tool": name, "arguments": arguments})
        return [types.TextContent(
            type="text", 
            text=f"❌ Error: {str(e)}\n\nError details: {error_result}"
        )]


# ==============================================================================
# Tool Implementation Functions
# ==============================================================================

async def _authenticate_mcp_server(
    server_url: str,
    user_id: str = "default",
    scopes: List[str] = None
) -> str:
    """MCP サーバーに対して認証を実行"""
    if scopes is None:
        scopes = ["read", "write"]
    
    try:
        # クライアントキーの生成
        client_key = f"{server_url}#{user_id}"
        
        # 設定の取得または作成
        config = _configurations.get(server_url, MCPClientConfig())
        
        # サーバー設定の作成・更新
        server_config = ServerConfig(
            url=server_url,
            scopes=scopes,
            name=f"MCP Server ({server_url})"
        )
        config.add_server(server_config)
        
        # 認証クライアントの作成
        auth_client = MCPAuthClient(server_url, user_id, config)
        
        # 認証状態のチェック
        async with auth_client:
            is_authenticated = await auth_client.is_authenticated()
            
            if is_authenticated:
                _auth_clients[client_key] = auth_client
                return f"""✅ Already authenticated to {server_url}
                
📋 **Server**: {server_url}
👤 **User**: {user_id}
🔐 **Status**: Authenticated
🎯 **Scopes**: {', '.join(scopes)}
⏰ **Checked**: {_get_current_time()}
"""
            
            # 認証フローの開始
            auth_url = await auth_client.start_authentication_flow()
            
            # クライアントを保存（認証完了待ち状態）
            _auth_clients[client_key] = auth_client
            
            return f"""🔐 Authentication required for {server_url}

📋 **Server**: {server_url}
👤 **User**: {user_id}
🎯 **Scopes**: {', '.join(scopes)}

🌐 **Please visit the following URL to authenticate:**
{auth_url}

⚠️ **Next Steps:**
1. Click the authentication URL above
2. Complete the OAuth flow in your browser  
3. Return here and use `make_authenticated_request` to verify authentication

💡 **Tip**: The authentication will be automatically handled for subsequent requests.
"""
            
    except Exception as e:
        logger.error(f"Authentication failed: {e}")
        raise


async def _make_authenticated_request(
    server_url: str,
    method: str,
    path: str,
    user_id: str = "default",
    headers: Dict[str, str] = None,
    json_data: Dict[str, Any] = None,
    query_params: Dict[str, str] = None
) -> str:
    """認証付きHTTPリクエストを実行"""
    if headers is None:
        headers = {}
    if query_params is None:
        query_params = {}
    
    try:
        client_key = f"{server_url}#{user_id}"
        
        # 既存のクライアントを取得または作成
        if client_key not in _auth_clients:
            config = _configurations.get(server_url, MCPClientConfig())
            auth_client = MCPAuthClient(server_url, user_id, config)
            _auth_clients[client_key] = auth_client
        else:
            auth_client = _auth_clients[client_key]
        
        # リクエスト実行
        async with auth_client:
            kwargs = {"headers": headers}
            
            if json_data:
                kwargs["json"] = json_data
            
            if query_params:
                kwargs["params"] = query_params
            
            response = await auth_client.make_authenticated_request(
                method, path, **kwargs
            )
            
            # レスポンス処理
            response_text = ""
            try:
                if response.headers.get("content-type", "").startswith("application/json"):
                    response_data = response.json()
                    response_text = json.dumps(response_data, indent=2, ensure_ascii=False)
                else:
                    response_text = response.text
            except:
                response_text = response.text
            
            return f"""✅ Request completed successfully

📋 **Request Details**:
- **Method**: {method}
- **URL**: {server_url}{path}
- **User**: {user_id}
- **Status**: {response.status_code}

📊 **Response**:
```json
{response_text[:1000]}{"..." if len(response_text) > 1000 else ""}
```

⏰ **Timestamp**: {_get_current_time()}
"""
            
    except Exception as e:
        logger.error(f"Authenticated request failed: {e}")
        
        # 認証エラーの場合は特別な処理
        if "AuthenticationRequired" in str(type(e)):
            return f"""🔐 Authentication required for {server_url}

❌ **Error**: {str(e)}

💡 **Solution**: Please run `authenticate_mcp_server` first:
```
authenticate_mcp_server(server_url="{server_url}", user_id="{user_id}")
```
"""
        else:
            raise


async def _check_auth_status(server_url: str, user_id: str = "default") -> str:
    """認証状態を確認"""
    try:
        client_key = f"{server_url}#{user_id}"
        
        if client_key not in _auth_clients:
            return f"""❌ No authentication found

📋 **Server**: {server_url}
👤 **User**: {user_id}
🔐 **Status**: Not authenticated

💡 **Next Steps**: Run `authenticate_mcp_server` to authenticate.
"""
        
        auth_client = _auth_clients[client_key]
        
        async with auth_client:
            is_authenticated = await auth_client.is_authenticated()
            
            # トークン情報の取得
            token_info = auth_client.token_manager.get_token_info()
            expires_in = auth_client.token_manager.get_expires_in()
            will_expire_soon = auth_client.token_manager.will_expire_soon()
            
            status_emoji = "✅" if is_authenticated else "❌"
            status_text = "Authenticated" if is_authenticated else "Not authenticated"
            
            result = f"""{status_emoji} Authentication Status

📋 **Server**: {server_url}
👤 **User**: {user_id}
🔐 **Status**: {status_text}
"""
            
            if is_authenticated and token_info:
                result += f"""
📊 **Token Info**:
- **Type**: {token_info.get('token_type', 'Unknown')}
- **Expires in**: {expires_in} seconds ({expires_in // 60} minutes)
- **Will expire soon**: {'Yes' if will_expire_soon else 'No'}
- **Scopes**: {token_info.get('scope', 'Unknown')}
"""
            
            result += f"\n⏰ **Checked**: {_get_current_time()}"
            return result
            
    except Exception as e:
        logger.error(f"Status check failed: {e}")
        raise


async def _revoke_authentication(server_url: str, user_id: str = "default") -> str:
    """認証を取り消し"""
    try:
        client_key = f"{server_url}#{user_id}"
        
        if client_key not in _auth_clients:
            return f"""ℹ️ No authentication to revoke

📋 **Server**: {server_url}
👤 **User**: {user_id}
🔐 **Status**: Already not authenticated
"""
        
        auth_client = _auth_clients[client_key]
        
        async with auth_client:
            success = await auth_client.revoke_authentication()
        
        if success:
            # クライアントを削除
            del _auth_clients[client_key]
            
            return f"""✅ Authentication revoked successfully

📋 **Server**: {server_url}
👤 **User**: {user_id}
🔐 **Status**: Revoked
⏰ **Timestamp**: {_get_current_time()}

💡 **Note**: All stored tokens have been securely deleted.
"""
        else:
            return f"""⚠️ Revocation completed with warnings

📋 **Server**: {server_url}
👤 **User**: {user_id}
🔐 **Status**: Revoked (with warnings)
⏰ **Timestamp**: {_get_current_time()}
"""
            
    except Exception as e:
        logger.error(f"Revocation failed: {e}")
        raise


async def _configure_mcp_client(server_url: str, config: Dict[str, Any]) -> str:
    """MCPクライアント設定を行う"""
    try:
        # 設定オブジェクトの作成
        mcp_config = MCPClientConfig(
            timeout=config.get("timeout", 30),
            max_retries=config.get("max_retries", 3),
            require_https=config.get("require_https", True)
        )
        
        # サーバー設定の作成
        server_config = ServerConfig(
            url=server_url,
            scopes=config.get("scopes", ["read", "write"]),
            redirect_uri=config.get("redirect_uri")
        )
        mcp_config.add_server(server_config)
        
        # 設定を保存
        _configurations[server_url] = mcp_config
        
        return f"""✅ MCP Client configured successfully

📋 **Server**: {server_url}
⚙️ **Configuration**:
- **Timeout**: {mcp_config.timeout} seconds
- **Max Retries**: {mcp_config.max_retries}
- **Require HTTPS**: {mcp_config.require_https}
- **Scopes**: {', '.join(server_config.scopes)}
- **Redirect URI**: {server_config.redirect_uri or 'Default'}

⏰ **Configured**: {_get_current_time()}

💡 **Note**: Configuration will be used for new authentication sessions.
"""
        
    except Exception as e:
        logger.error(f"Configuration failed: {e}")
        raise


async def _list_configured_servers() -> str:
    """設定済みサーバーの一覧を取得"""
    try:
        if not _auth_clients and not _configurations:
            return """ℹ️ No servers configured

💡 **Getting Started**:
1. Configure a server: `configure_mcp_client`
2. Authenticate: `authenticate_mcp_server`  
3. Make requests: `make_authenticated_request`
"""
        
        result = f"""📋 Configured Servers ({len(_configurations)} configs, {len(_auth_clients)} active sessions)

"""
        
        # 設定情報
        for server_url, config in _configurations.items():
            server_config = config.get_server_config(server_url)
            result += f"""🔧 **{server_url}**
   - Timeout: {config.timeout}s
   - Max Retries: {config.max_retries}
   - Scopes: {', '.join(server_config.scopes if server_config else ['read', 'write'])}
   - HTTPS Required: {config.require_https}

"""
        
        # アクティブセッション
        if _auth_clients:
            result += "🔐 **Active Sessions**:\n"
            for client_key in _auth_clients.keys():
                server_url, user_id = client_key.split('#', 1)
                result += f"   - {server_url} (user: {user_id})\n"
        
        result += f"\n⏰ **Listed**: {_get_current_time()}"
        
        return result
        
    except Exception as e:
        logger.error(f"List servers failed: {e}")
        raise


def _get_current_time() -> str:
    """現在時刻を取得"""
    from datetime import datetime
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


# ==============================================================================
# Server Startup
# ==============================================================================

async def main():
    """MCPサーバーのメイン関数"""
    # サーバー初期化オプション
    options = InitializationOptions(
        server_name="mcp-auth-client",
        server_version="1.0.0",
        capabilities=server.get_capabilities(
            notification_options=NotificationOptions(),
            experimental_capabilities={}
        )
    )
    
    # STDIOサーバーとして実行
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            options,
            raise_exceptions=True
        )


if __name__ == "__main__":
    """メイン実行部"""
    logger.info("Starting MCP Authentication Client Server...")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}")
        raise