import logging

def get_tools():
    try:
        from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset
        from google.adk.tools.mcp_tool import StreamableHTTPConnectionParams
        
        return [
            get_mcp_ada_tool(),
        ]
    except ImportError as e:
        logging.warning(f"MCP tools not available: {e}")
        return []


def get_mcp_ada_tool():
    try:
        from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset
        from google.adk.tools.mcp_tool import StreamableHTTPConnectionParams
        
        URL = "https://mcp-server-ad-analyzer-preview.adt-c1a.workers.dev/f1a677342aac2d95634b259b5f8e6ab1b01ce07323625ebd82ab5864e21827f7"

        logging.debug(f"load mcp ada tool: {URL}")

        return MCPToolset(
            connection_params=StreamableHTTPConnectionParams(
                url=URL,
            )
        )
    except ImportError as e:
        logging.warning(f"MCP Ada tool not available: {e}")
        return None
