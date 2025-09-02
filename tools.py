import logging
import os
import sys
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, StdioServerParameters
from google.adk.tools.mcp_tool import StreamableHTTPConnectionParams

# パスを追加してauth モジュールをインポート可能にする
sys.path.append(os.path.dirname(__file__))

def get_google_access_token():
    """Google認証トークンを安全に取得"""
    try:
        from auth.google_auth import get_google_access_token as _get_token
        return _get_token()
    except ImportError as e:
        logging.error(f"Google auth module not available: {e}")
        return None
    except Exception as e:
        logging.error(f"Failed to get Google access token: {e}")
        return None

def get_google_id_token():
    """Google IDトークンを安全に取得（MCP ADA用）"""
    try:
        from auth.google_auth import get_google_id_token as _get_id_token
        return _get_id_token()
    except ImportError as e:
        logging.error(f"Google auth module not available: {e}")
        return None
    except Exception as e:
        logging.error(f"Failed to get Google ID token: {e}")
        return None

def get_current_user_id_for_tools():
    """MCPツール用に現在のユーザーIDを取得"""
    try:
        from auth.google_auth import get_auth_manager
        
        auth_manager = get_auth_manager()
        is_authenticated, user_info = auth_manager.check_auth_status()
        
        if is_authenticated and user_info:
            return user_info.get("email", user_info.get("id"))
        
        return None
        
    except Exception as e:
        logging.error(f"Failed to get current user ID for tools: {e}")
        return None

def get_mcp_ada_access_token():
    """MCP ADA専用アクセストークンを安全に取得（ユーザー単位）"""
    try:
        from auth.mcp_ada_auth import get_mcp_ada_access_token as _get_token
        
        # 現在のユーザーIDを取得
        user_id = get_current_user_id_for_tools()
        if not user_id:
            logging.warning("No authenticated user found for MCP ADA access token")
            return None
            
        return _get_token(user_id)
    except ImportError as e:
        logging.error(f"MCP ADA auth module not available: {e}")
        return None
    except Exception as e:
        logging.error(f"Failed to get MCP ADA access token: {e}")
        return None


def get_tools():
    """MCPツールを安全に読み込み"""
    tools = []
    
    # MCPツールを有効化
    logging.info("Loading MCP tools with Google OAuth authentication")
    
    # MCP ADAツールを安全に追加
    try:
        ada_tool = get_mcp_ada_tool()
        if ada_tool:
            tools.append(ada_tool)
            logging.info("Successfully added MCP ADA tool")
    except Exception as e:
        logging.error(f"Failed to add MCP ADA tool: {str(e)}")
    
    # MCP PowerPointツールを安全に追加
    try:
        powerpoint_tool = get_mcp_powerpoint_tool()
        if powerpoint_tool:
            tools.append(powerpoint_tool)
            logging.info("Successfully added MCP PowerPoint tool")
    except Exception as e:
        logging.error(f"Failed to add MCP PowerPoint tool: {str(e)}")
    
    return tools


def get_mcp_ada_tool():
    """MCP ADAツールを安全に初期化"""
    try:
        URL = "https://mcp-server-ad-analyzer.adt-c1a.workers.dev/mcp"
        
        # MCP ADA専用アクセストークンを取得
        access_token = get_mcp_ada_access_token()
        
        if not access_token:
            logging.warning("Failed to get MCP ADA access token. Please run authentication first.")
            return None
        
        logging.debug(f"Initializing MCP ADA tool: {URL}")
        
        toolset = MCPToolset(
            connection_params=StreamableHTTPConnectionParams(
                url=URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                },
            )
        )
        
        logging.info("MCP ADA tool initialized successfully")
        return toolset
        
    except Exception as e:
        logging.error(f"Failed to initialize MCP ADA tool: {str(e)}")
        import traceback
        traceback.print_exc()
        return None


def get_mcp_powerpoint_tool():
    """MCP PowerPointツールを安全に初期化"""
    try:
        logging.debug("Initializing MCP PowerPoint tool")
        
        toolset = MCPToolset(
            connection_params=StdioServerParameters(
                command="npx",
                args=["-y", "@smithery/cli@latest", "run", "@GongRzhe/Office-PowerPoint-MCP-Server"],
            )
        )
        
        logging.info("MCP PowerPoint tool initialized successfully")
        return toolset
        
    except Exception as e:
        logging.error(f"Failed to initialize MCP PowerPoint tool: {str(e)}")
        import traceback
        traceback.print_exc()
        return None
