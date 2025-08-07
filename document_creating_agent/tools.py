import logging
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, StdioServerParameters
from google.adk.tools.mcp_tool import StreamableHTTPConnectionParams


def get_tools():
    return [
        # get_mcp_ada_tool(),
        get_mcp_powerpoint_tool(),
    ]


# def get_mcp_ada_tool():
#     URL = "https://mcp-server-ad-analyzer-preview.adt-c1a.workers.dev/f1a677342aac2d95634b259b5f8e6ab1b01ce07323625ebd82ab5864e21827f7"

#     logging.debug(f"load mcp ada tool: {URL}")

#     return MCPToolset(
#         connection_params=StreamableHTTPConnectionParams(
#             url=URL,
#         )
#     )    


# def get_mcp_powerpoint_tool():
#     logging.debug("load mcp powerpoint tool: Office-PowerPoint-MCP-Server")

#     return MCPToolset(
#         connection_params=StdioServerParameters(
#             command="npx",
#             args=["-y", "@smithery/cli@latest", "run", "@GongRzhe/Office-PowerPoint-MCP-Server"],
#         )
#     )

def get_mcp_powerpoint_tool():
    logging.debug("load mcp powerpoint tool: Office-PowerPoint-MCP-Server")

    return MCPToolset(
        connection_params=StdioServerParameters(
            command="npx",
            args=["-y", "@smithery/cli@latest", "run", "@GongRzhe/Office-PowerPoint-MCP-Server"],
        )
    )
