import logging
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, StdioServerParameters

def get_tools():
    return [
        get_mcp_powerpoint_tool(),
    ]


def get_mcp_powerpoint_tool():
    logging.debug("load mcp powerpoint tool: Office-PowerPoint-MCP-Server")

    return MCPToolset(
        connection_params=StdioServerParameters(
            command="npx",
            args=["-y", "@smithery/cli@latest", "run", "@GongRzhe/Office-PowerPoint-MCP-Server"],
        )
    )
