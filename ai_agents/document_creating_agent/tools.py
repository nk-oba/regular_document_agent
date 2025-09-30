import logging
import os
import sys
import csv
import io
from datetime import datetime, timedelta
from typing import Optional, Union
from google.adk.tools.agent_tool import AgentTool
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, StdioServerParameters
from google.adk.tools.mcp_tool import StreamableHTTPConnectionParams
from google.adk.tools.tool_context import ToolContext
from google.genai import types

from .sub_agents import slide_agent, playwright_agent, ds_agent

# Add path to make auth module importable
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from shared.auth.google_auth import get_google_access_token


def get_tools():
    """Safely load MCP tools (lazy initialization)"""
    tools = []

    # Add Artifact generation tools
    tools.extend([
        # call_playwright_agent,

        # make_mcp_authenticated_request_tool,
        # check_mcp_auth_status_tool

        # generate_sample_csv_report,

        # authenticate_mcp_server_tool,
        # make_mcp_authenticated_request_tool,
        # check_mcp_auth_status_tool
    ])

    
    # TODO: Replace with dynamic authentication
    mcp_toolset = None
    try:
        from shared.auth.mcp_ada_auth import get_mcp_ada_access_token
        access_token = get_mcp_ada_access_token(user_id="usr0302483@login.gmo-ap.jp")
        
        if access_token:
            mcp_toolset = MCPToolset(
                connection_params=StreamableHTTPConnectionParams(
                    url="https://mcp-server-ad-analyzer.adt-c1a.workers.dev/mcp",
                    headers={"Authorization": f"Bearer {access_token}"}
                )
            )
            logging.info("MCP ADA toolset initialized with valid access token")
        else:
            logging.warning("No valid MCP ADA access token available. MCP tools will not be initialized.")
            
    except Exception as e:
        logging.error(f"Failed to initialize MCP ADA toolset: {e}")

    # Add MCP ADA toolset to tools (only if authenticated)
    if mcp_toolset:
        tools.append(mcp_toolset)
        logging.info("MCP ADA toolset added to tools")

    # # Import and add list_tools function
    # try:
    #     from list_tools import list_tools
    #     tools.append(list_tools)
    # except ImportError as e:
    #     logging.warning(f"Failed to import list_tools: {e}")
    
    # Skip MCP tool initialization to prioritize server startup
    logging.info("MCP tools will be initialized on first use (lazy loading)")
    logging.info(f"Added {len(tools)} tools (including MCP toolset if authenticated)")
    
    # # If MCP ADA is authenticated, dynamically get actual tools from server
    # try:
    #     from mcp_dynamic_tools import create_mcp_ada_dynamic_tools
    #     dynamic_mcp_tools = create_mcp_ada_dynamic_tools()
        
    #     if dynamic_mcp_tools:
    #         tools.extend(dynamic_mcp_tools)
    #         logging.info(f"Added {len(dynamic_mcp_tools)} dynamic MCP ADA tools to available tools")
    #     else:
    #         logging.info("No MCP ADA tools available or not authenticated")
    # except Exception as e:
    #     logging.warning(f"Failed to load dynamic MCP ADA tools: {e}")
    
    return tools


def get_mcp_ada_tool():
    """Safely initialize MCP ADA tool"""
    try:
        URL = "https://mcp-server-ad-analyzer.adt-c1a.workers.dev/mcp"
        
        # Get access token with Google OAuth2.0
        access_token = get_google_access_token()
        
        if not access_token:
            logging.warning("Failed to get Google access token. Please run authentication first.")
            return None
        
        logging.debug(f"Initializing MCP ADA tool: {URL}")
        logging.debug(f"Using access token: {access_token[:20]}..." if access_token else "No access token")
        
        # Debug: Log header information
        headers = {"Authorization": f"Bearer {access_token}"}
        logging.debug(f"Request headers: {headers}")
        
        toolset = MCPToolset(
            connection_params=StreamableHTTPConnectionParams(
                url=URL,
                headers=headers,
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
    """Safely initialize MCP PowerPoint tool"""
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


async def generate_sample_csv_report(tool_context):
    """
    Generate a sample CSV report and save it as a downloadable Artifact
    
    Args:
        tool_context: ADK tool context
        
    Returns:
        str: Information about the generated CSV file
    """
    try:
        # Generate test sample data
        sample_data = [
            ["Campaign ID", "Campaign Name", "Impressions", "Clicks", "CTR (%)", "Cost (JPY)", "CPC (JPY)", "Date"],
            ["12345", "Summer Sale Campaign", "125,000", "3,200", "2.56", "48,000", "15", "2024-08-15"],
            ["12346", "New Product Launch", "89,500", "2,150", "2.40", "32,250", "15", "2024-08-16"],
            ["12347", "Back to School", "156,300", "4,890", "3.13", "73,350", "15", "2024-08-17"],
            ["12348", "Weekend Flash Sale", "203,100", "6,093", "3.00", "91,395", "15", "2024-08-18"],
            ["12349", "Outlet Clearance", "78,900", "1,578", "2.00", "23,670", "15", "2024-08-19"]
        ]
        
        # Generate CSV data in byte format
        csv_buffer = io.StringIO()
        csv_writer = csv.writer(csv_buffer)
        csv_writer.writerows(sample_data)
        csv_bytes = csv_buffer.getvalue().encode('utf-8-sig')  # UTF-8 with BOM for Excel compatibility
        
        # Create as ADK Artifact
        csv_artifact = types.Part.from_bytes(
            data=csv_bytes,
            mime_type="text/csv"
        )
        
        # Include timestamp in filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"advertising_campaign_report_{timestamp}.csv"
        
        # Use new helper function to save Artifact
        import sys
        import os
        sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        from shared.utils.artifact_user_helper import save_artifact_with_proper_user_id, format_download_section
        
        # Save Artifact with proper user management
        save_result = await save_artifact_with_proper_user_id(
            tool_context=tool_context,
            filename=filename,
            artifact=csv_artifact,
            return_detailed_info=True
        )
        
        if save_result['success']:
            logging.info(f"CSV report generated successfully: {filename} (version {save_result['version']})")
            # Get formatted download section
            download_section = format_download_section(save_result)
            version = save_result['version']
        else:
            logging.error(f"Failed to save CSV artifact: {save_result.get('error')}")
            download_section = f"❌ File save error: {save_result.get('error', 'Unknown error')}"
            version = 0
        
        return f"""✅ CSV report generated successfully!

📄 **Filename**: `{filename}`
📊 **Data**: 5 sample advertising campaign data entries
🔢 **Version**: {version}
🕐 **Generated at**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

{download_section}

📊 **Included data**:
- Campaign ID, Campaign Name
- Impressions, Clicks
- CTR (Click-through rate), Ad cost
- CPC (Cost per click), Execution date

💡 This file can be opened directly in Excel for analysis!
"""
        
    except Exception as e:
        error_msg = f"Error occurred while generating CSV: {str(e)}"
        logging.error(error_msg)
        import traceback
        traceback.print_exc()
        return error_msg



# ==============================================================================
# MCP Authentication Tool Integration
# ==============================================================================

async def authenticate_mcp_server_tool(
    tool_context,
    server_url: str,
    user_id: Optional[str] = None,
    scopes: Optional[list[str]] = None
):
    """
    Tool to execute MCP ADA compliant OAuth 2.1 authentication
    
    Args:
        tool_context: ADK tool context
        server_url: MCP server URL to authenticate with
        user_id: User ID (automatically retrieved from session if not specified)
        scopes: List of requested scopes (default: ["mcp:reports", "mcp:properties"])
        
    Returns:
        str: Authentication result message
    """
    try:
        # Auto-retrieve user ID from session info (if user_id is not specified)
        if user_id is None:
            from session_user_helper import get_user_id_from_session
            user_id = get_user_id_from_session(tool_context)
        
        # Import MCP authentication toolset
        sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        from mcp_client.mcp_toolset import authenticate_mcp_server_helper
        
        # Set MCP ADA specific scopes as default
        if scopes is None:
            scopes = ["mcp:reports", "mcp:properties"]
        
        logging.info(f"Authenticating to MCP server: {server_url} (user: {user_id}, scopes: {scopes})")
        
        # Execute MCP authentication
        result = await authenticate_mcp_server_helper(server_url, user_id, scopes)
        
        logging.info(f"MCP authentication completed for {server_url}")
        return result
        
    except ImportError as e:
        error_msg = f"❌ MCP authentication tool is not available: {e}\n\n💡 Please verify that the MCP authentication framework is correctly installed."
        logging.error(error_msg)
        return error_msg
    except Exception as e:
        error_msg = f"❌ Error occurred during MCP authentication: {str(e)}"
        logging.error(error_msg)
        import traceback
        traceback.print_exc()
        return error_msg


async def make_mcp_authenticated_request_tool(
    tool_context,
    server_url: str,
    method: str,
    path: str,
    user_id: Optional[str] = None,
    headers: Optional[dict] = None,
    json_data: Optional[dict] = None,
    query_params: Optional[dict] = None
):
    """
    Tool to execute MCP authenticated HTTP requests
    
    Args:
        tool_context: ADK tool context
        server_url: MCP server URL
        method: HTTP method (GET, POST, PUT, DELETE, PATCH)
        path: Request path
        user_id: User ID (automatically retrieved from session if not specified)
        headers: Additional HTTP headers
        json_data: JSON body data
        query_params: Query parameters
        
    Returns:
        str: Request result
    """
    try:
        # Auto-retrieve user ID from session info (if user_id is not specified)
        if user_id is None:
            from session_user_helper import get_user_id_from_session
            user_id = get_user_id_from_session(tool_context)
        # Import MCP authentication toolset
        sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        from mcp_client.mcp_toolset import mcp_request_helper
        
        # Prepare parameters
        kwargs = {}
        if headers:
            kwargs["headers"] = headers
        if json_data:
            kwargs["json"] = json_data
        if query_params:
            kwargs["params"] = query_params
        
        logging.info(f"Making authenticated request: {method} {server_url}{path} (user: {user_id})")
        
        # Execute MCP authenticated request
        result = await mcp_request_helper(
            server_url,
            method.upper(),
            path,
            user_id,
            **kwargs
        )
        
        logging.info(f"MCP request completed: {method} {server_url}{path}")
        return result
        
    except ImportError as e:
        error_msg = f"❌ MCP authentication tool is not available: {e}\n\n💡 Please verify that the MCP authentication framework is correctly installed."
        logging.error(error_msg)
        return error_msg
    except Exception as e:
        error_msg = f"❌ Error occurred during MCP authenticated request: {str(e)}"
        logging.error(error_msg)
        import traceback
        traceback.print_exc()
        return error_msg


async def check_mcp_auth_status_tool(
    tool_context,
    server_url: str,
    user_id: Optional[str] = None
):
    """
    Tool to check MCP authentication status
    
    Args:
        tool_context: ADK tool context
        server_url: MCP server URL
        user_id: User ID (automatically retrieved from session if not specified)
        
    Returns:
        str: Authentication status information
    """
    try:
        # Auto-retrieve user ID from session info (if user_id is not specified)
        if user_id is None:
            from session_user_helper import get_user_id_from_session
            user_id = get_user_id_from_session(tool_context)
        # Import MCP authentication toolset
        sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        from mcp_client.mcp_toolset import get_mcp_auth_toolset
        
        logging.info(f"Checking auth status for: {server_url} (user: {user_id})")
        
        # Check authentication status
        auth_toolset = get_mcp_auth_toolset()
        status_result = await auth_toolset.check_status(server_url, user_id)
        
        # Format result
        if status_result.get("authenticated"):
            result = f"""✅ Authentication status check completed

{status_result.get('result', '')}

💡 **Status**: Authenticated
🌐 **Server**: {server_url}
👤 **User**: {user_id}
"""
        else:
            result = f"""❌ Authentication required

🌐 **Server**: {server_url}
👤 **User**: {user_id}
🔐 **Status**: Not authenticated

💡 **Next step**: 
```
authenticate_mcp_server_tool("{server_url}", "{user_id}")
```
Please run to authenticate.

Error details: {status_result.get('error', 'Unknown error')}
"""
        
        logging.info(f"Auth status check completed for {server_url}")
        return result
        
    except ImportError as e:
        error_msg = f"❌ MCP authentication tool is not available: {e}\n\n💡 Please verify that the MCP authentication framework is correctly installed."
        logging.error(error_msg)
        return error_msg
    except Exception as e:
        error_msg = f"❌ Error occurred during MCP authentication status check: {str(e)}"
        logging.error(error_msg)
        import traceback
        traceback.print_exc()
        return error_msg



## ==============================================================================

# Configuration consideration agent call
async def call_playwright_agent(
    ad_report_data: dict,
    tool_context: ToolContext,
):
    """
    Tool to call playwright agent.

    This tool creates and returns an outline for document structure.    
    """

    if ad_report_data == "N/A":
        return tool_context.state["playwright_agent_output"]

    agent_tool = AgentTool(agent=playwright_agent)

    ad_with_data = f"""
    The JSON data to be used for structure consideration is as follows:

    {ad_report_data}
    """

    playwright_agent_output = await agent_tool.run_async(
        args={
            "request": ad_with_data,
        },
        tool_context=tool_context,
    )
    tool_context.state["playwright_agent_output"] = playwright_agent_output
    return playwright_agent_output


# Document creation agent call
async def call_slide_agent(
    outline: str,
    ad_report_data: dict,
    tool_context: ToolContext,
):
    """Tool to call slide agent."""

    if ad_report_data == "N/A":
        return tool_context.state["slide_agent_output"]

    if outline == "N/A":
        return tool_context.state["slide_agent_output"]

    outline_with_data = f"""
    Please create a pptx presentation file from the following markdown text and JSON data.

    The structure of the presentation to be created is as follows:
    {outline}

    The advertising data to be embedded in the presentation is as follows:
    {ad_report_data}
    """

    agent_tool = AgentTool(agent=slide_agent)
    slide_agent_output = await agent_tool.run_async(
        args={
            "request": outline_with_data,
        },
        tool_context=tool_context,
    )
    tool_context.state["slide_agent_output"] = slide_agent_output
    return slide_agent_output

# Analysis agent call
async def call_ds_agent(
    question: str,
    tool_context: ToolContext,
):
    """Tool to call data science (nl2py) agent with progress tracking."""

    async def progress_callback(event_type: str, message: str):
        """Log progress events for monitoring."""
        logging.info(f"[DS Agent Progress] {event_type}: {message}")
        # TODO: Future extension point to send progress via WebSocket or SSE

    if question == "N/A":
        await progress_callback("cache_hit", "Returning cached result")
        return tool_context.state.get("ds_agent_output", "No previous data science agent output available")

    input_data = tool_context.state.get("csv_report_output")
    question_with_data = f"""
  Question to answer: {question}

  Actual data to analyze previous question is already in the following:
  {input_data}

  """

    try:
        await progress_callback("start", "Starting data analysis...")

        # Use AgentTool for stable execution
        agent_tool = AgentTool(agent=ds_agent)

        await progress_callback("processing", "Executing data analysis...")
        logging.info("Calling ds_agent via AgentTool.run_async")

        ds_agent_output = await agent_tool.run_async(
            args={"request": question_with_data},
            tool_context=tool_context
        )

        await progress_callback("complete", "Data analysis completed")
        logging.info("ds_agent completed successfully")

        # Save result to state
        tool_context.state["ds_agent_output"] = ds_agent_output

        return ds_agent_output

    except Exception as e:
        error_msg = f"An error occurred during data analysis: {str(e)}"
        await progress_callback("error", error_msg)
        logging.error(error_msg, exc_info=True)
        return {"status": "ERROR", "error": error_msg}

async def execute_get_ad_report(tool_context=None):
    """
    Tool to return sample advertising report numerical data in JSON format

    Args:
        tool_context: ADK tool context (optional)

    Returns:
        dict: Sample advertising report data
    """
    try:
        sample_ad_report = {
            "status": "SUCCESS",
            "data": {
            "report_metadata": {
                "report_id": "RPT-2024-0824-001",
                "report_name": "Monthly Advertising Operations Report",
                "period": {
                    "start_date": "2024-08-01",
                    "end_date": "2024-08-31"
                },
                "generated_at": "2024-09-01T10:00:00+09:00",
                "currency": "JPY"
            },
            "summary": {
                "total_impressions": 1542800,
                "total_clicks": 38570,
                "total_cost": 578550,
                "average_ctr": 2.50,
                "average_cpc": 15,
                "average_cpm": 375,
                "conversion_count": 856,
                "conversion_rate": 2.22,
                "cost_per_conversion": 676
            },
            "campaigns": [
                {
                    "campaign_id": "12345",
                    "campaign_name": "Summer Sale Campaign",
                    "campaign_type": "Search Ads",
                    "status": "active",
                    "start_date": "2024-08-01",
                    "end_date": "2024-08-15",
                    "metrics": {
                        "impressions": 460000,
                        "clicks": 12000,
                        "cost": 180000,
                        "ctr": 2.61,
                        "cpc": 15,
                        "cpm": 391,
                        "conversions": 267,
                        "conversion_rate": 2.23,
                        "cost_per_conversion": 674
                    },
                    "ad_groups": [
                        {
                            "ad_group_id": "AG101",
                            "ad_group_name": "Summer Sale_Search_Main",
                            "impressions": 280000,
                            "clicks": 7200,
                            "cost": 108000,
                            "ctr": 2.57,
                            "cpc": 15,
                            "conversions": 160,
                            "conversion_rate": 2.22,
                            "daily_data": [
                                {"date": "2024-08-01", "impressions": 18666, "clicks": 480, "cost": 7200, "ctr": 2.57, "cpc": 15, "conversions": 11},
                                {"date": "2024-08-02", "impressions": 18667, "clicks": 480, "cost": 7200, "ctr": 2.57, "cpc": 15, "conversions": 10},
                                {"date": "2024-08-03", "impressions": 18667, "clicks": 480, "cost": 7200, "ctr": 2.57, "cpc": 15, "conversions": 12},
                                {"date": "2024-08-04", "impressions": 18666, "clicks": 480, "cost": 7200, "ctr": 2.57, "cpc": 15, "conversions": 11},
                                {"date": "2024-08-05", "impressions": 18667, "clicks": 480, "cost": 7200, "ctr": 2.57, "cpc": 15, "conversions": 10},
                                {"date": "2024-08-06", "impressions": 18667, "clicks": 480, "cost": 7200, "ctr": 2.57, "cpc": 15, "conversions": 11},
                                {"date": "2024-08-07", "impressions": 18666, "clicks": 480, "cost": 7200, "ctr": 2.57, "cpc": 15, "conversions": 12},
                                {"date": "2024-08-08", "impressions": 18667, "clicks": 480, "cost": 7200, "ctr": 2.57, "cpc": 15, "conversions": 10},
                                {"date": "2024-08-09", "impressions": 18667, "clicks": 480, "cost": 7200, "ctr": 2.57, "cpc": 15, "conversions": 11},
                                {"date": "2024-08-10", "impressions": 18666, "clicks": 480, "cost": 7200, "ctr": 2.57, "cpc": 15, "conversions": 10},
                                {"date": "2024-08-11", "impressions": 18667, "clicks": 480, "cost": 7200, "ctr": 2.57, "cpc": 15, "conversions": 12},
                                {"date": "2024-08-12", "impressions": 18667, "clicks": 480, "cost": 7200, "ctr": 2.57, "cpc": 15, "conversions": 11},
                                {"date": "2024-08-13", "impressions": 18666, "clicks": 480, "cost": 7200, "ctr": 2.57, "cpc": 15, "conversions": 10},
                                {"date": "2024-08-14", "impressions": 18667, "clicks": 480, "cost": 7200, "ctr": 2.57, "cpc": 15, "conversions": 11},
                                {"date": "2024-08-15", "impressions": 18666, "clicks": 480, "cost": 7200, "ctr": 2.57, "cpc": 15, "conversions": 10}
                            ]
                        },
                        {
                            "ad_group_id": "AG102",
                            "ad_group_name": "Summer Sale_Search_Sub",
                            "impressions": 180000,
                            "clicks": 4800,
                            "cost": 72000,
                            "ctr": 2.67,
                            "cpc": 15,
                            "conversions": 107,
                            "conversion_rate": 2.23,
                            "daily_data": [
                                {"date": "2024-08-01", "impressions": 12000, "clicks": 320, "cost": 4800, "ctr": 2.67, "cpc": 15, "conversions": 7},
                                {"date": "2024-08-02", "impressions": 12000, "clicks": 320, "cost": 4800, "ctr": 2.67, "cpc": 15, "conversions": 8},
                                {"date": "2024-08-03", "impressions": 12000, "clicks": 320, "cost": 4800, "ctr": 2.67, "cpc": 15, "conversions": 7},
                                {"date": "2024-08-04", "impressions": 12000, "clicks": 320, "cost": 4800, "ctr": 2.67, "cpc": 15, "conversions": 7},
                                {"date": "2024-08-05", "impressions": 12000, "clicks": 320, "cost": 4800, "ctr": 2.67, "cpc": 15, "conversions": 8},
                                {"date": "2024-08-06", "impressions": 12000, "clicks": 320, "cost": 4800, "ctr": 2.67, "cpc": 15, "conversions": 7},
                                {"date": "2024-08-07", "impressions": 12000, "clicks": 320, "cost": 4800, "ctr": 2.67, "cpc": 15, "conversions": 8},
                                {"date": "2024-08-08", "impressions": 12000, "clicks": 320, "cost": 4800, "ctr": 2.67, "cpc": 15, "conversions": 7},
                                {"date": "2024-08-09", "impressions": 12000, "clicks": 320, "cost": 4800, "ctr": 2.67, "cpc": 15, "conversions": 7},
                                {"date": "2024-08-10", "impressions": 12000, "clicks": 320, "cost": 4800, "ctr": 2.67, "cpc": 15, "conversions": 8},
                                {"date": "2024-08-11", "impressions": 12000, "clicks": 320, "cost": 4800, "ctr": 2.67, "cpc": 15, "conversions": 7},
                                {"date": "2024-08-12", "impressions": 12000, "clicks": 320, "cost": 4800, "ctr": 2.67, "cpc": 15, "conversions": 8},
                                {"date": "2024-08-13", "impressions": 12000, "clicks": 320, "cost": 4800, "ctr": 2.67, "cpc": 15, "conversions": 7},
                                {"date": "2024-08-14", "impressions": 12000, "clicks": 320, "cost": 4800, "ctr": 2.67, "cpc": 15, "conversions": 7},
                                {"date": "2024-08-15", "impressions": 12000, "clicks": 320, "cost": 4800, "ctr": 2.67, "cpc": 15, "conversions": 8}
                            ]
                        }
                    ]
                },
                {
                    "campaign_id": "12346",
                    "campaign_name": "New Product Launch",
                    "campaign_type": "Display Ads",
                    "status": "active",
                    "start_date": "2024-08-16",
                    "end_date": "2024-08-31",
                    "metrics": {
                        "impressions": 512000,
                        "clicks": 12000,
                        "cost": 180000,
                        "ctr": 2.34,
                        "cpc": 15,
                        "cpm": 352,
                        "conversions": 264,
                        "conversion_rate": 2.20,
                        "cost_per_conversion": 682
                    },
                    "ad_groups": [
                        {
                            "ad_group_id": "AG201",
                            "ad_group_name": "New Product Banner_Main",
                            "impressions": 320000,
                            "clicks": 7680,
                            "cost": 115200,
                            "ctr": 2.40,
                            "cpc": 15,
                            "conversions": 169,
                            "conversion_rate": 2.20,
                            "daily_data": [
                                {"date": "2024-08-16", "impressions": 20000, "clicks": 480, "cost": 7200, "ctr": 2.40, "cpc": 15, "conversions": 11},
                                {"date": "2024-08-17", "impressions": 20000, "clicks": 480, "cost": 7200, "ctr": 2.40, "cpc": 15, "conversions": 10},
                                {"date": "2024-08-18", "impressions": 20000, "clicks": 480, "cost": 7200, "ctr": 2.40, "cpc": 15, "conversions": 12},
                                {"date": "2024-08-19", "impressions": 20000, "clicks": 480, "cost": 7200, "ctr": 2.40, "cpc": 15, "conversions": 11},
                                {"date": "2024-08-20", "impressions": 20000, "clicks": 480, "cost": 7200, "ctr": 2.40, "cpc": 15, "conversions": 10},
                                {"date": "2024-08-21", "impressions": 20000, "clicks": 480, "cost": 7200, "ctr": 2.40, "cpc": 15, "conversions": 11},
                                {"date": "2024-08-22", "impressions": 20000, "clicks": 480, "cost": 7200, "ctr": 2.40, "cpc": 15, "conversions": 12},
                                {"date": "2024-08-23", "impressions": 20000, "clicks": 480, "cost": 7200, "ctr": 2.40, "cpc": 15, "conversions": 10},
                                {"date": "2024-08-24", "impressions": 20000, "clicks": 480, "cost": 7200, "ctr": 2.40, "cpc": 15, "conversions": 11},
                                {"date": "2024-08-25", "impressions": 20000, "clicks": 480, "cost": 7200, "ctr": 2.40, "cpc": 15, "conversions": 10},
                                {"date": "2024-08-26", "impressions": 20000, "clicks": 480, "cost": 7200, "ctr": 2.40, "cpc": 15, "conversions": 12},
                                {"date": "2024-08-27", "impressions": 20000, "clicks": 480, "cost": 7200, "ctr": 2.40, "cpc": 15, "conversions": 11},
                                {"date": "2024-08-28", "impressions": 20000, "clicks": 480, "cost": 7200, "ctr": 2.40, "cpc": 15, "conversions": 10},
                                {"date": "2024-08-29", "impressions": 20000, "clicks": 480, "cost": 7200, "ctr": 2.40, "cpc": 15, "conversions": 11},
                                {"date": "2024-08-30", "impressions": 20000, "clicks": 480, "cost": 7200, "ctr": 2.40, "cpc": 15, "conversions": 10},
                                {"date": "2024-08-31", "impressions": 20000, "clicks": 480, "cost": 7200, "ctr": 2.40, "cpc": 15, "conversions": 9}
                            ]
                        },
                        {
                            "ad_group_id": "AG202",
                            "ad_group_name": "New Product Banner_Sub",
                            "impressions": 192000,
                            "clicks": 4320,
                            "cost": 64800,
                            "ctr": 2.25,
                            "cpc": 15,
                            "conversions": 95,
                            "conversion_rate": 2.20,
                            "daily_data": [
                                {"date": "2024-08-16", "impressions": 12000, "clicks": 270, "cost": 4050, "ctr": 2.25, "cpc": 15, "conversions": 6},
                                {"date": "2024-08-17", "impressions": 12000, "clicks": 270, "cost": 4050, "ctr": 2.25, "cpc": 15, "conversions": 5},
                                {"date": "2024-08-18", "impressions": 12000, "clicks": 270, "cost": 4050, "ctr": 2.25, "cpc": 15, "conversions": 7},
                                {"date": "2024-08-19", "impressions": 12000, "clicks": 270, "cost": 4050, "ctr": 2.25, "cpc": 15, "conversions": 6},
                                {"date": "2024-08-20", "impressions": 12000, "clicks": 270, "cost": 4050, "ctr": 2.25, "cpc": 15, "conversions": 5},
                                {"date": "2024-08-21", "impressions": 12000, "clicks": 270, "cost": 4050, "ctr": 2.25, "cpc": 15, "conversions": 6},
                                {"date": "2024-08-22", "impressions": 12000, "clicks": 270, "cost": 4050, "ctr": 2.25, "cpc": 15, "conversions": 7},
                                {"date": "2024-08-23", "impressions": 12000, "clicks": 270, "cost": 4050, "ctr": 2.25, "cpc": 15, "conversions": 5},
                                {"date": "2024-08-24", "impressions": 12000, "clicks": 270, "cost": 4050, "ctr": 2.25, "cpc": 15, "conversions": 6},
                                {"date": "2024-08-25", "impressions": 12000, "clicks": 270, "cost": 4050, "ctr": 2.25, "cpc": 15, "conversions": 5},
                                {"date": "2024-08-26", "impressions": 12000, "clicks": 270, "cost": 4050, "ctr": 2.25, "cpc": 15, "conversions": 7},
                                {"date": "2024-08-27", "impressions": 12000, "clicks": 270, "cost": 4050, "ctr": 2.25, "cpc": 15, "conversions": 6},
                                {"date": "2024-08-28", "impressions": 12000, "clicks": 270, "cost": 4050, "ctr": 2.25, "cpc": 15, "conversions": 5},
                                {"date": "2024-08-29", "impressions": 12000, "clicks": 270, "cost": 4050, "ctr": 2.25, "cpc": 15, "conversions": 6},
                                {"date": "2024-08-30", "impressions": 12000, "clicks": 270, "cost": 4050, "ctr": 2.25, "cpc": 15, "conversions": 5},
                                {"date": "2024-08-31", "impressions": 12000, "clicks": 270, "cost": 4050, "ctr": 2.25, "cpc": 15, "conversions": 5}
                            ]
                        }
                    ]
                },
                {
                    "campaign_id": "12347",
                    "campaign_name": "Back to School",
                    "campaign_type": "Video Ads",
                    "status": "active",
                    "start_date": "2024-08-01",
                    "end_date": "2024-08-31",
                    "metrics": {
                        "impressions": 570800,
                        "clicks": 14570,
                        "cost": 218550,
                        "ctr": 2.55,
                        "cpc": 15,
                        "cpm": 383,
                        "conversions": 325,
                        "conversion_rate": 2.23,
                        "cost_per_conversion": 673
                    },
                    "ad_groups": [
                        {
                            "ad_group_id": "AG301",
                            "ad_group_name": "Back to School_Video_15sec",
                            "impressions": 342480,
                            "clicks": 8742,
                            "cost": 131130,
                            "ctr": 2.55,
                            "cpc": 15,
                            "conversions": 195,
                            "conversion_rate": 2.23,
                            "daily_data": [
                                {"date": "2024-08-01", "impressions": 11048, "clicks": 282, "cost": 4230, "ctr": 2.55, "cpc": 15, "conversions": 6},
                                {"date": "2024-08-02", "impressions": 11048, "clicks": 282, "cost": 4230, "ctr": 2.55, "cpc": 15, "conversions": 7},
                                {"date": "2024-08-03", "impressions": 11049, "clicks": 282, "cost": 4230, "ctr": 2.55, "cpc": 15, "conversions": 6},
                                {"date": "2024-08-04", "impressions": 11048, "clicks": 282, "cost": 4230, "ctr": 2.55, "cpc": 15, "conversions": 6},
                                {"date": "2024-08-05", "impressions": 11048, "clicks": 282, "cost": 4230, "ctr": 2.55, "cpc": 15, "conversions": 7},
                                {"date": "2024-08-06", "impressions": 11049, "clicks": 282, "cost": 4230, "ctr": 2.55, "cpc": 15, "conversions": 6},
                                {"date": "2024-08-07", "impressions": 11048, "clicks": 282, "cost": 4230, "ctr": 2.55, "cpc": 15, "conversions": 7},
                                {"date": "2024-08-08", "impressions": 11048, "clicks": 282, "cost": 4230, "ctr": 2.55, "cpc": 15, "conversions": 6},
                                {"date": "2024-08-09", "impressions": 11049, "clicks": 282, "cost": 4230, "ctr": 2.55, "cpc": 15, "conversions": 6},
                                {"date": "2024-08-10", "impressions": 11048, "clicks": 282, "cost": 4230, "ctr": 2.55, "cpc": 15, "conversions": 7},
                                {"date": "2024-08-11", "impressions": 11048, "clicks": 282, "cost": 4230, "ctr": 2.55, "cpc": 15, "conversions": 6},
                                {"date": "2024-08-12", "impressions": 11049, "clicks": 282, "cost": 4230, "ctr": 2.55, "cpc": 15, "conversions": 7},
                                {"date": "2024-08-13", "impressions": 11048, "clicks": 282, "cost": 4230, "ctr": 2.55, "cpc": 15, "conversions": 6},
                                {"date": "2024-08-14", "impressions": 11048, "clicks": 282, "cost": 4230, "ctr": 2.55, "cpc": 15, "conversions": 6},
                                {"date": "2024-08-15", "impressions": 11049, "clicks": 282, "cost": 4230, "ctr": 2.55, "cpc": 15, "conversions": 7},
                                {"date": "2024-08-16", "impressions": 11048, "clicks": 282, "cost": 4230, "ctr": 2.55, "cpc": 15, "conversions": 6},
                                {"date": "2024-08-17", "impressions": 11048, "clicks": 282, "cost": 4230, "ctr": 2.55, "cpc": 15, "conversions": 7},
                                {"date": "2024-08-18", "impressions": 11049, "clicks": 282, "cost": 4230, "ctr": 2.55, "cpc": 15, "conversions": 6},
                                {"date": "2024-08-19", "impressions": 11048, "clicks": 282, "cost": 4230, "ctr": 2.55, "cpc": 15, "conversions": 6},
                                {"date": "2024-08-20", "impressions": 11048, "clicks": 282, "cost": 4230, "ctr": 2.55, "cpc": 15, "conversions": 7},
                                {"date": "2024-08-21", "impressions": 11049, "clicks": 282, "cost": 4230, "ctr": 2.55, "cpc": 15, "conversions": 6},
                                {"date": "2024-08-22", "impressions": 11048, "clicks": 282, "cost": 4230, "ctr": 2.55, "cpc": 15, "conversions": 7},
                                {"date": "2024-08-23", "impressions": 11048, "clicks": 282, "cost": 4230, "ctr": 2.55, "cpc": 15, "conversions": 6},
                                {"date": "2024-08-24", "impressions": 11049, "clicks": 282, "cost": 4230, "ctr": 2.55, "cpc": 15, "conversions": 6},
                                {"date": "2024-08-25", "impressions": 11048, "clicks": 282, "cost": 4230, "ctr": 2.55, "cpc": 15, "conversions": 7},
                                {"date": "2024-08-26", "impressions": 11048, "clicks": 282, "cost": 4230, "ctr": 2.55, "cpc": 15, "conversions": 6},
                                {"date": "2024-08-27", "impressions": 11049, "clicks": 282, "cost": 4230, "ctr": 2.55, "cpc": 15, "conversions": 7},
                                {"date": "2024-08-28", "impressions": 11048, "clicks": 282, "cost": 4230, "ctr": 2.55, "cpc": 15, "conversions": 6},
                                {"date": "2024-08-29", "impressions": 11048, "clicks": 282, "cost": 4230, "ctr": 2.55, "cpc": 15, "conversions": 6},
                                {"date": "2024-08-30", "impressions": 11049, "clicks": 282, "cost": 4230, "ctr": 2.55, "cpc": 15, "conversions": 7},
                                {"date": "2024-08-31", "impressions": 11048, "clicks": 282, "cost": 4230, "ctr": 2.55, "cpc": 15, "conversions": 6}
                            ]
                        },
                        {
                            "ad_group_id": "AG302",
                            "ad_group_name": "Back to School_Video_30sec",
                            "impressions": 228320,
                            "clicks": 5828,
                            "cost": 87420,
                            "ctr": 2.55,
                            "cpc": 15,
                            "conversions": 130,
                            "conversion_rate": 2.23,
                            "daily_data": [
                                {"date": "2024-08-01", "impressions": 7365, "clicks": 188, "cost": 2820, "ctr": 2.55, "cpc": 15, "conversions": 4},
                                {"date": "2024-08-02", "impressions": 7365, "clicks": 188, "cost": 2820, "ctr": 2.55, "cpc": 15, "conversions": 5},
                                {"date": "2024-08-03", "impressions": 7366, "clicks": 188, "cost": 2820, "ctr": 2.55, "cpc": 15, "conversions": 4},
                                {"date": "2024-08-04", "impressions": 7365, "clicks": 188, "cost": 2820, "ctr": 2.55, "cpc": 15, "conversions": 4},
                                {"date": "2024-08-05", "impressions": 7365, "clicks": 188, "cost": 2820, "ctr": 2.55, "cpc": 15, "conversions": 5},
                                {"date": "2024-08-06", "impressions": 7366, "clicks": 188, "cost": 2820, "ctr": 2.55, "cpc": 15, "conversions": 4},
                                {"date": "2024-08-07", "impressions": 7365, "clicks": 188, "cost": 2820, "ctr": 2.55, "cpc": 15, "conversions": 5},
                                {"date": "2024-08-08", "impressions": 7365, "clicks": 188, "cost": 2820, "ctr": 2.55, "cpc": 15, "conversions": 4},
                                {"date": "2024-08-09", "impressions": 7366, "clicks": 188, "cost": 2820, "ctr": 2.55, "cpc": 15, "conversions": 4},
                                {"date": "2024-08-10", "impressions": 7365, "clicks": 188, "cost": 2820, "ctr": 2.55, "cpc": 15, "conversions": 5},
                                {"date": "2024-08-11", "impressions": 7365, "clicks": 188, "cost": 2820, "ctr": 2.55, "cpc": 15, "conversions": 4},
                                {"date": "2024-08-12", "impressions": 7366, "clicks": 188, "cost": 2820, "ctr": 2.55, "cpc": 15, "conversions": 5},
                                {"date": "2024-08-13", "impressions": 7365, "clicks": 188, "cost": 2820, "ctr": 2.55, "cpc": 15, "conversions": 4},
                                {"date": "2024-08-14", "impressions": 7365, "clicks": 188, "cost": 2820, "ctr": 2.55, "cpc": 15, "conversions": 4},
                                {"date": "2024-08-15", "impressions": 7366, "clicks": 188, "cost": 2820, "ctr": 2.55, "cpc": 15, "conversions": 5},
                                {"date": "2024-08-16", "impressions": 7365, "clicks": 188, "cost": 2820, "ctr": 2.55, "cpc": 15, "conversions": 4},
                                {"date": "2024-08-17", "impressions": 7365, "clicks": 188, "cost": 2820, "ctr": 2.55, "cpc": 15, "conversions": 5},
                                {"date": "2024-08-18", "impressions": 7366, "clicks": 188, "cost": 2820, "ctr": 2.55, "cpc": 15, "conversions": 4},
                                {"date": "2024-08-19", "impressions": 7365, "clicks": 188, "cost": 2820, "ctr": 2.55, "cpc": 15, "conversions": 4},
                                {"date": "2024-08-20", "impressions": 7365, "clicks": 188, "cost": 2820, "ctr": 2.55, "cpc": 15, "conversions": 5},
                                {"date": "2024-08-21", "impressions": 7366, "clicks": 188, "cost": 2820, "ctr": 2.55, "cpc": 15, "conversions": 4},
                                {"date": "2024-08-22", "impressions": 7365, "clicks": 188, "cost": 2820, "ctr": 2.55, "cpc": 15, "conversions": 5},
                                {"date": "2024-08-23", "impressions": 7365, "clicks": 188, "cost": 2820, "ctr": 2.55, "cpc": 15, "conversions": 4},
                                {"date": "2024-08-24", "impressions": 7366, "clicks": 188, "cost": 2820, "ctr": 2.55, "cpc": 15, "conversions": 4},
                                {"date": "2024-08-25", "impressions": 7365, "clicks": 188, "cost": 2820, "ctr": 2.55, "cpc": 15, "conversions": 5},
                                {"date": "2024-08-26", "impressions": 7365, "clicks": 188, "cost": 2820, "ctr": 2.55, "cpc": 15, "conversions": 4},
                                {"date": "2024-08-27", "impressions": 7366, "clicks": 188, "cost": 2820, "ctr": 2.55, "cpc": 15, "conversions": 5},
                                {"date": "2024-08-28", "impressions": 7365, "clicks": 188, "cost": 2820, "ctr": 2.55, "cpc": 15, "conversions": 4},
                                {"date": "2024-08-29", "impressions": 7365, "clicks": 188, "cost": 2820, "ctr": 2.55, "cpc": 15, "conversions": 4},
                                {"date": "2024-08-30", "impressions": 7366, "clicks": 188, "cost": 2820, "ctr": 2.55, "cpc": 15, "conversions": 5},
                                {"date": "2024-08-31", "impressions": 7365, "clicks": 188, "cost": 2820, "ctr": 2.55, "cpc": 15, "conversions": 4}
                            ]
                        }
                    ]
                }
            ],
            "daily_summary": [
                {"date": "2024-08-01", "total_impressions": 49713, "total_clicks": 1242, "total_cost": 18630, "average_ctr": 2.50, "average_cpc": 15, "conversion_count": 28, "conversion_rate": 2.25},
                {"date": "2024-08-02", "total_impressions": 49713, "total_clicks": 1242, "total_cost": 18630, "average_ctr": 2.50, "average_cpc": 15, "conversion_count": 30, "conversion_rate": 2.41},
                {"date": "2024-08-03", "total_impressions": 49715, "total_clicks": 1242, "total_cost": 18630, "average_ctr": 2.50, "average_cpc": 15, "conversion_count": 29, "conversion_rate": 2.34},
                {"date": "2024-08-04", "total_impressions": 49713, "total_clicks": 1242, "total_cost": 18630, "average_ctr": 2.50, "average_cpc": 15, "conversion_count": 26, "conversion_rate": 2.09},
                {"date": "2024-08-05", "total_impressions": 49713, "total_clicks": 1242, "total_cost": 18630, "average_ctr": 2.50, "average_cpc": 15, "conversion_count": 30, "conversion_rate": 2.41},
                {"date": "2024-08-06", "total_impressions": 49715, "total_clicks": 1242, "total_cost": 18630, "average_ctr": 2.50, "average_cpc": 15, "conversion_count": 28, "conversion_rate": 2.25},
                {"date": "2024-08-07", "total_impressions": 49713, "total_clicks": 1242, "total_cost": 18630, "average_ctr": 2.50, "average_cpc": 15, "conversion_count": 32, "conversion_rate": 2.58},
                {"date": "2024-08-08", "total_impressions": 49713, "total_clicks": 1242, "total_cost": 18630, "average_ctr": 2.50, "average_cpc": 15, "conversion_count": 27, "conversion_rate": 2.17},
                {"date": "2024-08-09", "total_impressions": 49715, "total_clicks": 1242, "total_cost": 18630, "average_ctr": 2.50, "average_cpc": 15, "conversion_count": 28, "conversion_rate": 2.25},
                {"date": "2024-08-10", "total_impressions": 49713, "total_clicks": 1242, "total_cost": 18630, "average_ctr": 2.50, "average_cpc": 15, "conversion_count": 30, "conversion_rate": 2.41},
                {"date": "2024-08-11", "total_impressions": 49713, "total_clicks": 1242, "total_cost": 18630, "average_ctr": 2.50, "average_cpc": 15, "conversion_count": 29, "conversion_rate": 2.34},
                {"date": "2024-08-12", "total_impressions": 49715, "total_clicks": 1242, "total_cost": 18630, "average_ctr": 2.50, "average_cpc": 15, "conversion_count": 31, "conversion_rate": 2.50},
                {"date": "2024-08-13", "total_impressions": 49713, "total_clicks": 1242, "total_cost": 18630, "average_ctr": 2.50, "average_cpc": 15, "conversion_count": 27, "conversion_rate": 2.17},
                {"date": "2024-08-14", "total_impressions": 49713, "total_clicks": 1242, "total_cost": 18630, "average_ctr": 2.50, "average_cpc": 15, "conversion_count": 28, "conversion_rate": 2.25},
                {"date": "2024-08-15", "total_impressions": 49715, "total_clicks": 1242, "total_cost": 18630, "average_ctr": 2.50, "average_cpc": 15, "conversion_count": 30, "conversion_rate": 2.41},
                {"date": "2024-08-16", "total_impressions": 51413, "total_clicks": 1220, "total_cost": 18300, "average_ctr": 2.37, "average_cpc": 15, "conversion_count": 27, "conversion_rate": 2.21},
                {"date": "2024-08-17", "total_impressions": 51413, "total_clicks": 1220, "total_cost": 18300, "average_ctr": 2.37, "average_cpc": 15, "conversion_count": 27, "conversion_rate": 2.21},
                {"date": "2024-08-18", "total_impressions": 51415, "total_clicks": 1220, "total_cost": 18300, "average_ctr": 2.37, "average_cpc": 15, "conversion_count": 29, "conversion_rate": 2.38},
                {"date": "2024-08-19", "total_impressions": 51413, "total_clicks": 1220, "total_cost": 18300, "average_ctr": 2.37, "average_cpc": 15, "conversion_count": 27, "conversion_rate": 2.21},
                {"date": "2024-08-20", "total_impressions": 51413, "total_clicks": 1220, "total_cost": 18300, "average_ctr": 2.37, "average_cpc": 15, "conversion_count": 27, "conversion_rate": 2.21},
                {"date": "2024-08-21", "total_impressions": 51415, "total_clicks": 1220, "total_cost": 18300, "average_ctr": 2.37, "average_cpc": 15, "conversion_count": 27, "conversion_rate": 2.21},
                {"date": "2024-08-22", "total_impressions": 51413, "total_clicks": 1220, "total_cost": 18300, "average_ctr": 2.37, "average_cpc": 15, "conversion_count": 29, "conversion_rate": 2.38},
                {"date": "2024-08-23", "total_impressions": 51413, "total_clicks": 1220, "total_cost": 18300, "average_ctr": 2.37, "average_cpc": 15, "conversion_count": 25, "conversion_rate": 2.05},
                {"date": "2024-08-24", "total_impressions": 51415, "total_clicks": 1220, "total_cost": 18300, "average_ctr": 2.37, "average_cpc": 15, "conversion_count": 27, "conversion_rate": 2.21},
                {"date": "2024-08-25", "total_impressions": 51413, "total_clicks": 1220, "total_cost": 18300, "average_ctr": 2.37, "average_cpc": 15, "conversion_count": 27, "conversion_rate": 2.21},
                {"date": "2024-08-26", "total_impressions": 51413, "total_clicks": 1220, "total_cost": 18300, "average_ctr": 2.37, "average_cpc": 15, "conversion_count": 29, "conversion_rate": 2.38},
                {"date": "2024-08-27", "total_impressions": 51415, "total_clicks": 1220, "total_cost": 18300, "average_ctr": 2.37, "average_cpc": 15, "conversion_count": 29, "conversion_rate": 2.38},
                {"date": "2024-08-28", "total_impressions": 51413, "total_clicks": 1220, "total_cost": 18300, "average_ctr": 2.37, "average_cpc": 15, "conversion_count": 25, "conversion_rate": 2.05},
                {"date": "2024-08-29", "total_impressions": 51413, "total_clicks": 1220, "total_cost": 18300, "average_ctr": 2.37, "average_cpc": 15, "conversion_count": 27, "conversion_rate": 2.21},
                {"date": "2024-08-30", "total_impressions": 51415, "total_clicks": 1220, "total_cost": 18300, "average_ctr": 2.37, "average_cpc": 15, "conversion_count": 27, "conversion_rate": 2.21},
                {"date": "2024-08-31", "total_impressions": 51413, "total_clicks": 1220, "total_cost": 18300, "average_ctr": 2.37, "average_cpc": 15, "conversion_count": 24, "conversion_rate": 1.97}
            ],
            "recommendations": [
                {
                    "type": "campaign_optimization",
                    "priority": "high",
                    "title": "Increase Budget for Summer Sale Campaign",
                    "description": "The Summer Sale Campaign shows the highest CTR (2.61%). Increasing the budget by 20% could acquire more conversions.",
                    "expected_impact": "Conversion count +18%, CTR maintained"
                },
                {
                    "type": "ad_group_optimization",
                    "priority": "medium",
                    "title": "Improve New Product Banner_Sub Ad Group",
                    "description": "The New Product Banner_Sub ad group shows a low CTR of 2.25%. We recommend reviewing the creative to bring it closer to the main ad group's performance.",
                    "expected_impact": "CTR +0.15%, Conversion count +5%"
                }
            ]
            }
        }

        return sample_ad_report

    except Exception as e:
        error_msg = f"Error occurred while generating sample advertising report JSON: {str(e)}"
        return {"status": "ERROR", "error": error_msg}
