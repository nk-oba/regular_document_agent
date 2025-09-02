import logging
import os
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, StdioServerParameters
from google.adk.tools.mcp_tool import StreamableHTTPConnectionParams


def get_tools():
    """MCPツールを安全に読み込み"""
    tools = []
    
    # MCPツールを一時的に無効化（デバッグ用）
    logging.info("MCP tools temporarily disabled for debugging")
    return tools
    
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
        
        # 環境変数から認証トークンを取得
        auth_token = os.getenv("MCP_ADA_AUTH_TOKEN")
        
        if not auth_token:
            logging.warning("MCP_ADA_AUTH_TOKEN not found in environment variables")
            return None
        
        logging.debug(f"Initializing MCP ADA tool: {URL}")
        
        toolset = MCPToolset(
            connection_params=StreamableHTTPConnectionParams(
                url=URL,
                headers={
                    "Authorization": f"Bearer {auth_token}",
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
