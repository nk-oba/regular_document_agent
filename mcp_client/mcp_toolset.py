"""
MCPツールセット統合
既存のGoogle ADKツールシステムとの統合
"""

import logging
import sys
import os
from typing import Optional, Dict, Any
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, StdioServerParameters

# パス設定
current_dir = os.path.dirname(__file__)
project_root = os.path.dirname(os.path.dirname(current_dir))
sys.path.append(project_root)

logger = logging.getLogger(__name__)


class MCPAuthToolset:
    """MCP認証ツールセット
    
    Google ADKのMCPToolsetと統合して使用する
    """
    
    def __init__(self):
        self._toolset: Optional[MCPToolset] = None
        self._initialized = False
    
    def get_mcp_auth_toolset(self) -> Optional[MCPToolset]:
        """MCP認証ツールセットを安全に初期化して取得"""
        if self._initialized:
            return self._toolset
        
        try:
            logger.info("Initializing MCP Auth Client toolset...")
            
            # MCP認証クライアントサーバーのパス
            mcp_server_path = os.path.join(current_dir, "mcp_server.py")
            
            if not os.path.exists(mcp_server_path):
                logger.error(f"MCP server script not found: {mcp_server_path}")
                return None
            
            # STDIOサーバーパラメータを作成
            server_params = StdioServerParameters(
                command="python",
                args=["-m", "agents.mcp_client.mcp_server"],
                cwd=project_root,
                env={
                    "PYTHONPATH": project_root,
                    "MCP_CLIENT_LOG_LEVEL": "INFO"
                }
            )
            
            # MCPToolsetを初期化
            self._toolset = MCPToolset(connection_params=server_params)
            self._initialized = True
            
            logger.info("MCP Auth Client toolset initialized successfully")
            return self._toolset
            
        except Exception as e:
            logger.error(f"Failed to initialize MCP Auth Client toolset: {e}")
            import traceback
            traceback.print_exc()
            self._initialized = True  # エラーでも再試行を避けるため
            return None
    
    async def authenticate_server(
        self, 
        server_url: str, 
        user_id: str = "default", 
        scopes: list = None
    ) -> Dict[str, Any]:
        """MCPサーバーに対して認証を実行
        
        Args:
            server_url: 認証対象のMCPサーバーURL
            user_id: ユーザーID
            scopes: 要求するスコープ
            
        Returns:
            Dict[str, Any]: 認証結果
        """
        if scopes is None:
            scopes = ["read", "write"]
        
        toolset = self.get_mcp_auth_toolset()
        if not toolset:
            return {
                "success": False,
                "error": "MCP Auth toolset not available"
            }
        
        try:
            # ツールを取得して実行
            tools = await toolset.get_tools()
            auth_tool = next((tool for tool in tools if tool.name == "authenticate_mcp_server"), None)
            
            if not auth_tool:
                return {
                    "success": False,
                    "error": "authenticate_mcp_server tool not found"
                }
            
            # 認証ツールを呼び出し (Google ADKのToolContextが必要)
            from google.adk.tools.tool_context import ToolContext
            tool_context = ToolContext()
            
            result = await auth_tool.run_async(
                args={
                    "server_url": server_url,
                    "user_id": user_id,
                    "scopes": scopes
                },
                tool_context=tool_context
            )
            
            return {
                "success": True,
                "result": result,
                "server_url": server_url,
                "user_id": user_id
            }
            
        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "server_url": server_url,
                "user_id": user_id
            }
    
    async def make_request(
        self,
        server_url: str,
        method: str,
        path: str,
        user_id: str = "default",
        **kwargs
    ) -> Dict[str, Any]:
        """認証付きHTTPリクエストを実行
        
        Args:
            server_url: MCPサーバーURL
            method: HTTPメソッド
            path: リクエストパス
            user_id: ユーザーID
            **kwargs: 追加のリクエストパラメータ
            
        Returns:
            Dict[str, Any]: レスポンス結果
        """
        toolset = self.get_mcp_auth_toolset()
        if not toolset:
            return {
                "success": False,
                "error": "MCP Auth toolset not available"
            }
        
        try:
            # リクエストパラメータを準備
            request_params = {
                "server_url": server_url,
                "method": method.upper(),
                "path": path,
                "user_id": user_id
            }
            
            # 追加パラメータの処理
            if "headers" in kwargs:
                request_params["headers"] = kwargs["headers"]
            if "json" in kwargs:
                request_params["json_data"] = kwargs["json"]
            if "params" in kwargs:
                request_params["query_params"] = kwargs["params"]
            
            # ツールを取得して実行
            tools = await toolset.get_tools()
            request_tool = next((tool for tool in tools if tool.name == "make_authenticated_request"), None)
            
            if not request_tool:
                return {
                    "success": False,
                    "error": "make_authenticated_request tool not found"
                }
            
            # 認証付きリクエストを実行
            from google.adk.tools.tool_context import ToolContext
            tool_context = ToolContext()
            
            result = await request_tool.run_async(
                args=request_params,
                tool_context=tool_context
            )
            
            return {
                "success": True,
                "result": result,
                "server_url": server_url,
                "method": method,
                "path": path
            }
            
        except Exception as e:
            logger.error(f"Authenticated request failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "server_url": server_url,
                "method": method,
                "path": path
            }
    
    async def check_status(self, server_url: str, user_id: str = "default") -> Dict[str, Any]:
        """認証状態を確認
        
        Args:
            server_url: MCPサーバーURL
            user_id: ユーザーID
            
        Returns:
            Dict[str, Any]: 認証状態情報
        """
        toolset = self.get_mcp_auth_toolset()
        if not toolset:
            return {
                "authenticated": False,
                "error": "MCP Auth toolset not available"
            }
        
        try:
            # ツールを取得して実行
            tools = await toolset.get_tools()
            status_tool = next((tool for tool in tools if tool.name == "check_auth_status"), None)
            
            if not status_tool:
                return {
                    "authenticated": False,
                    "error": "check_auth_status tool not found"
                }
            
            from google.adk.tools.tool_context import ToolContext
            tool_context = ToolContext()
            
            result = await status_tool.run_async(
                args={
                    "server_url": server_url,
                    "user_id": user_id
                },
                tool_context=tool_context
            )
            
            # 結果をパース（簡単な文字列パターンマッチング）
            is_authenticated = "✅" in str(result) and "Authenticated" in str(result)
            
            return {
                "authenticated": is_authenticated,
                "result": result,
                "server_url": server_url,
                "user_id": user_id
            }
            
        except Exception as e:
            logger.error(f"Status check failed: {e}")
            return {
                "authenticated": False,
                "error": str(e),
                "server_url": server_url,
                "user_id": user_id
            }


# グローバルインスタンス
_mcp_auth_toolset: Optional[MCPAuthToolset] = None


def get_mcp_auth_toolset() -> MCPAuthToolset:
    """MCPAuthToolsetのグローバルインスタンスを取得"""
    global _mcp_auth_toolset
    
    if _mcp_auth_toolset is None:
        _mcp_auth_toolset = MCPAuthToolset()
    
    return _mcp_auth_toolset


# ==============================================================================
# 既存ツールシステムとの統合ヘルパー関数
# ==============================================================================

def add_mcp_auth_tools_to_agent():
    """エージェントのツール群にMCP認証ツールを追加する便利関数"""
    try:
        auth_toolset = get_mcp_auth_toolset()
        mcp_toolset = auth_toolset.get_mcp_auth_toolset()
        
        if mcp_toolset:
            logger.info("MCP Auth tools available and ready")
            return mcp_toolset
        else:
            logger.warning("MCP Auth tools not available")
            return None
            
    except Exception as e:
        logger.error(f"Failed to add MCP Auth tools: {e}")
        return None


async def authenticate_mcp_server_helper(
    server_url: str, 
    user_id: str = "default", 
    scopes: list = None
) -> str:
    """MCP認証のヘルパー関数
    
    既存のツール関数と同様のシグネチャで使用可能
    
    Args:
        server_url: MCPサーバーURL
        user_id: ユーザーID
        scopes: スコープリスト
        
    Returns:
        str: 認証結果メッセージ
    """
    auth_toolset = get_mcp_auth_toolset()
    result = await auth_toolset.authenticate_server(server_url, user_id, scopes)
    
    if result["success"]:
        return f"""✅ MCP Authentication completed
        
{result['result']}
"""
    else:
        return f"""❌ MCP Authentication failed

Server: {server_url}
User: {user_id}
Error: {result['error']}

💡 Please check the server URL and try again.
"""


async def mcp_request_helper(
    server_url: str,
    method: str,
    path: str,
    user_id: str = "default",
    **kwargs
) -> str:
    """MCP認証付きリクエストのヘルパー関数
    
    Args:
        server_url: MCPサーバーURL
        method: HTTPメソッド
        path: リクエストパス
        user_id: ユーザーID
        **kwargs: 追加のリクエストパラメータ
        
    Returns:
        str: リクエスト結果
    """
    auth_toolset = get_mcp_auth_toolset()
    result = await auth_toolset.make_request(server_url, method, path, user_id, **kwargs)
    
    if result["success"]:
        return f"""✅ MCP Request completed

{result['result']}
"""
    else:
        return f"""❌ MCP Request failed

Server: {server_url}
Method: {method} {path}
User: {user_id}
Error: {result['error']}

💡 You may need to authenticate first:
```
authenticate_mcp_server("{server_url}", "{user_id}")
```
"""


# ==============================================================================
# 統合テスト用関数
# ==============================================================================

async def test_mcp_auth_integration():
    """MCP認証統合のテスト関数"""
    try:
        logger.info("Testing MCP Auth integration...")
        
        # テスト用サーバーURL
        test_server = "https://httpbin.org"
        test_user = "test_user"
        
        auth_toolset = get_mcp_auth_toolset()
        
        # 1. 認証状態チェック
        logger.info("1. Checking authentication status...")
        status = await auth_toolset.check_status(test_server, test_user)
        logger.info(f"Status check result: {status}")
        
        # 2. 認証実行（テスト）
        logger.info("2. Testing authentication...")
        auth_result = await auth_toolset.authenticate_server(
            test_server, 
            test_user, 
            ["read"]
        )
        logger.info(f"Auth result: {auth_result}")
        
        # 3. リクエスト実行（テスト）
        logger.info("3. Testing authenticated request...")
        request_result = await auth_toolset.make_request(
            test_server,
            "GET",
            "/headers",
            test_user
        )
        logger.info(f"Request result: {request_result}")
        
        return True
        
    except Exception as e:
        logger.error(f"Integration test failed: {e}")
        return False


if __name__ == "__main__":
    """テスト実行"""
    import asyncio
    
    logging.basicConfig(level=logging.INFO)
    
    async def main():
        success = await test_mcp_auth_integration()
        if success:
            logger.info("✅ Integration test completed")
        else:
            logger.error("❌ Integration test failed")
    
    asyncio.run(main())