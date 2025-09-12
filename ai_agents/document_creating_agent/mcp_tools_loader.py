"""
MCP ADAツールを動的にロードする機能
認証済みの場合、MCPが提供するツールを自動的にtoolsに追加
"""
import logging
import sys
import os
from typing import List, Any

# パスを追加してsharedモジュールをインポート可能にする
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

logger = logging.getLogger(__name__)

def load_mcp_ada_tools_if_authenticated(tool_context=None) -> List[Any]:
    """
    MCP ADAが認証済みの場合、提供されるツールをロード
    
    Args:
        tool_context: ADK tool context（セッション情報の取得に使用）
        
    Returns:
        List[Any]: ロードされたMCPツールのリスト
    """
    mcp_tools = []
    
    try:
        # セッション情報からユーザーIDを取得
        if tool_context:
            from session_user_helper import get_user_id_from_session
            user_id = get_user_id_from_session(tool_context)
        else:
            # フォールバック: 既知の認証ファイルを探す
            user_id = _find_authenticated_user_id()
        
        if not user_id or user_id == "default":
            logger.info("No authenticated user found, skipping MCP tools loading")
            return []
        
        # MCP ADA認証マネージャーで認証状態をチェック
        from shared.auth.mcp_ada_auth import get_mcp_ada_auth_manager
        
        auth_manager = get_mcp_ada_auth_manager(user_id)
        access_token = auth_manager.get_access_token()
        
        if not access_token:
            logger.info(f"No valid MCP ADA token for user {user_id}, skipping MCP tools loading")
            return []
        
        # MCPツールセットを初期化
        from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset
        from google.adk.tools.mcp_tool import StreamableHTTPConnectionParams
        
        URL = "https://mcp-server-ad-analyzer.adt-c1a.workers.dev/mcp"
        
        toolset = MCPToolset(
            connection_params=StreamableHTTPConnectionParams(
                url=URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                },
            )
        )
        
        # MCPツールセットを取得して、ADK互換のツールとして変換
        # MCPToolsetは直接toolsを提供するのではなく、
        # MCP通信のためのセットアップを行う
        
        # 実際のMCPツール機能を取得するには、MCPサーバーに対して
        # tools/listリクエストを送信する必要がある
        
        # 現在の実装では、MCPToolset自体をtoolsとして返すのではなく、
        # MCPサーバーが提供する個別のツール機能をADK Functionとして
        # ラップする必要がある
        
        logger.info(f"MCP ADA toolset initialized for user {user_id}")
        logger.warning("Note: This returns the toolset, not individual MCP tools")
        
        # MCPToolset自体を返す（これは実際のMCPツールではない）
        return [toolset]
        
    except Exception as e:
        logger.warning(f"Failed to load MCP ADA tools: {e}")
        return []


def _find_authenticated_user_id() -> str:
    """
    認証ファイルから認証済みユーザーIDを検出
    
    Returns:
        str: 認証済みユーザーID、見つからない場合は"default"
    """
    try:
        import os
        import json
        import time
        from pathlib import Path
        
        # MCP ADA認証ディレクトリをチェック
        auth_dir = Path("auth_storage/mcp_ada_auth")
        
        if not auth_dir.exists():
            return "default"
        
        current_time = time.time()
        
        # 有効な認証ファイルを探す
        for cred_file in auth_dir.glob("mcp_ada_credentials_*.json"):
            try:
                with open(cred_file, 'r') as f:
                    cred_data = json.load(f)
                
                # トークンの有効期限をチェック
                if cred_data.get('expires_at', 0) > current_time:
                    # ファイル名からユーザーIDを抽出
                    # mcp_ada_credentials_{user_id}.json -> {user_id}
                    user_id = cred_file.stem.replace('mcp_ada_credentials_', '')
                    logger.info(f"Found authenticated user from file: {user_id}")
                    return user_id
                    
            except Exception as file_error:
                logger.debug(f"Failed to check credentials file {cred_file}: {file_error}")
                continue
        
        logger.info("No valid MCP ADA credentials found")
        return "default"
        
    except Exception as e:
        logger.warning(f"Failed to find authenticated user ID: {e}")
        return "default"


def get_mcp_tools_with_auth_check(tool_context=None) -> List[Any]:
    """
    認証チェック付きでMCPツールを取得
    
    Args:
        tool_context: ADK tool context
        
    Returns:
        List[Any]: 利用可能なMCPツールのリスト
    """
    try:
        return load_mcp_ada_tools_if_authenticated(tool_context)
    except Exception as e:
        logger.error(f"Error getting MCP tools with auth check: {e}")
        return []