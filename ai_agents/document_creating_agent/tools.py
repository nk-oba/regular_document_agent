import logging
import os
import sys
import csv
import io
import json
from datetime import datetime, timedelta
from typing import Optional, Union
from google.adk.tools.agent_tool import AgentTool
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, StdioServerParameters
from google.adk.tools.mcp_tool import StreamableHTTPConnectionParams
from google.adk.tools.tool_context import ToolContext
from google.auth.transport import Request
from google.genai import types
from shared.auth.oauth2_abstraction import OAuth2Credentials, create_oauth2_credentials
from shared.auth.oauth2_config import get_token_uri

from .sub_agents import slide_agent, playwright_agent, ds_agent

# Add path to make auth module importable
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from shared.auth.google_auth import get_google_access_token
from shared.auth.mcp_ada_adk_auth import (
    get_mcp_ada_token_from_state,
    TOKEN_CACHE_KEY
)


def resolve_mcp_user_id(adk_user_id: str) -> str:
    """
    Resolve ADK user_id (Google ID like '118276712451334561681') to MCP user_id (email)

    Args:
        adk_user_id: ADK user ID from tool_context.state or session

    Returns:
        Email address for MCP authentication, or adk_user_id if not found
    """
    logging.debug(f"[resolve_mcp_user_id] Input ADK user_id: {adk_user_id}")

    try:
        import sys
        import os
        sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        
        # First, try to get email from auth_sessions.db
        db_path = "auth_storage/auth_sessions.db"
        logging.debug(f"[resolve_mcp_user_id] Checking database: {db_path}")

        if os.path.exists(db_path):
            import sqlite3

            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Look up email from login_sessions joined with adk_sessions
            cursor.execute("""
                SELECT ls.email
                FROM login_sessions ls
                JOIN adk_sessions ads ON ls.id = ads.login_session_id
                WHERE ads.adk_user_id = ?
                ORDER BY ls.created_at DESC
                LIMIT 1
            """, (adk_user_id,))

            result = cursor.fetchone()
            conn.close()

            if result and result[0]:
                email = result[0]
                logging.info(f"[resolve_mcp_user_id] ✓ Resolved ADK user_id {adk_user_id} to email: {email}")
                return email
            else:
                logging.debug(f"[resolve_mcp_user_id] No email found in database for {adk_user_id}")
        else:
            logging.debug(f"[resolve_mcp_user_id] Database not found: {db_path}")
        
        # Fallback: try to get email from session files
        sessions_dir = "auth_storage/sessions/auth_sessions"
        logging.debug(f"[resolve_mcp_user_id] Checking session files: {sessions_dir}")

        if os.path.exists(sessions_dir):
            import json
            import glob

            # Look for session files that might contain user info
            session_files = glob.glob(os.path.join(sessions_dir, "*.json"))
            logging.debug(f"[resolve_mcp_user_id] Found {len(session_files)} session files")

            for session_file in session_files:
                try:
                    with open(session_file, 'r') as f:
                        session_data = json.load(f)

                    # Check if this session contains the user_id we're looking for
                    user_info = session_data.get('user_info', {})
                    if user_info.get('email'):
                        # Generate ADK user ID from email to compare
                        import hashlib
                        normalized_email = user_info['email'].strip().lower()
                        file_adk_user_id = hashlib.sha256(normalized_email.encode('utf-8')).hexdigest()[:16]

                        if file_adk_user_id == adk_user_id:
                            logging.info(f"[resolve_mcp_user_id] ✓ Resolved ADK user_id {adk_user_id} to email from file: {user_info['email']}")
                            return user_info['email']

                except Exception as e:
                    logging.debug(f"[resolve_mcp_user_id] Failed to read session file {session_file}: {e}")
                    continue
        else:
            logging.debug(f"[resolve_mcp_user_id] Session directory not found: {sessions_dir}")

        logging.warning(f"[resolve_mcp_user_id] Could not resolve ADK user_id {adk_user_id} to email, using as-is")
        return adk_user_id

    except Exception as e:
        import traceback
        logging.error(f"[resolve_mcp_user_id] Error resolving user_id: {e}")
        logging.debug(f"[resolve_mcp_user_id] Exception: {traceback.format_exc()}")
        return adk_user_id


def get_tools():
    """Safely load MCP tools (lazy initialization)"""
    tools = []

    # Add Artifact generation tools
    tools.extend([
        # call_playwright_agent,

        make_mcp_authenticated_request_tool,
        check_mcp_auth_status_tool,

        # generate_sample_csv_report,

        authenticate_mcp_server_tool,
        make_mcp_authenticated_request_tool,
        check_mcp_auth_status_tool
    ])

    # Add MCP ADA dynamic tools
    try:
        from .mcp_dynamic_tools import create_mcp_ada_dynamic_tools
        mcp_tools = create_mcp_ada_dynamic_tools()
        if mcp_tools:
            tools.extend(mcp_tools)
            logging.info(f"Added {len(mcp_tools)} MCP ADA dynamic tools")
    except Exception as e:
        logging.warning(f"Failed to load MCP ADA dynamic tools: {e}")

    logging.info(f"Total tools loaded: {len(tools)}")

    return tools





# ==============================================================================
# MCP Authentication Tool Integration
# ==============================================================================

async def authenticate_mcp_server_tool(
    tool_context: ToolContext,
    server_url: str = "https://mcp-server-ad-analyzer.adt-c1a.workers.dev/mcp",
    user_id: Optional[str] = None,
    scopes: Optional[list[str]] = None
):
    """
    Tool to execute MCP ADA compliant OAuth 2.1 authentication using ADK standard method

    Args:
        tool_context: ADK tool context with session state
        server_url: MCP server URL to authenticate with
        user_id: User ID (automatically retrieved from tool_context if not specified)
        scopes: List of requested scopes (default: ["mcp:reports", "mcp:properties"])

    Returns:
        dict: Authentication result with status and message
    """
    try:
        # Get user ID from tool_context if not provided
        if user_id is None:
            user_id = tool_context.state.get("user_id", "default")

        # Check if already authenticated
        access_token = get_mcp_ada_token_from_state(tool_context.state)

        if access_token:
            return {
                'success': True,
                'authenticated': True,
                'message': f'Already authenticated for MCP ADA server (user: {user_id})'
            }

        # Direct user to web-based authentication
        logging.info(f"MCP ADA authentication required for user: {user_id}")

        auth_url = f"http://localhost:8000/auth/mcp-ada/start"

        return {
            'success': False,
            'authenticated': False,
            'message': f'Please authenticate via web interface: {auth_url}',
            'auth_url': auth_url,
            'instructions': [
                f'1. Visit: {auth_url}',
                '2. Complete OAuth2 flow',
                '3. Retry this tool'
            ]
        }


    except Exception as e:
        error_msg = f"❌ Error occurred during MCP authentication: {str(e)}"
        logging.error(error_msg)
        import traceback
        traceback.print_exc()
        return {
            'success': False,
            'error': True,
            'message': error_msg
        }


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
            user_id = tool_context.state.get("user_id", "default")
        
        # Resolve ADK user_id to MCP user_id (email)
        mcp_user_id = resolve_mcp_user_id(user_id)
        
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
        
        logging.info(f"Making authenticated request: {method} {server_url}{path} (user: {mcp_user_id})")
        
        # Execute MCP authenticated request
        result = await mcp_request_helper(
            server_url,
            method.upper(),
            path,
            mcp_user_id,
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
    tool_context: ToolContext,
    server_url: str = "https://mcp-server-ad-analyzer.adt-c1a.workers.dev/mcp",
    user_id: Optional[str] = None
):
    """
    Tool to check MCP ADA authentication status using ADK session state

    Args:
        tool_context: ADK tool context with session state
        server_url: MCP server URL
        user_id: User ID (automatically retrieved from tool_context if not specified)

    Returns:
        dict: Authentication status information
    """
    try:
        logging.info("[check_mcp_auth_status_tool] === Checking MCP ADA auth status ===")
        # tool_context.stateの情報をデバッグ
        state_dict = tool_context.state.to_dict()
        logging.debug(f"[check_mcp_auth_status_tool] tool_context.state: {state_dict}")

        # Get user ID from tool_context if not provided
        if user_id is None:
            user_id = tool_context.state.get("user_id", "default")
            logging.debug(f"[check_mcp_auth_status_tool] Retrieved user_id from state: {user_id}")

        # Resolve ADK user_id (Google ID) to MCP user_id (email)
        mcp_user_id = resolve_mcp_user_id(user_id)

        logging.info(f"Checking MCP ADA auth status for user: {user_id} (resolved to: {mcp_user_id})")

        # Check for access token in ADK session state
        access_token = get_mcp_ada_token_from_state(tool_context.state)

        # If not in session, try file-based storage with resolved email
        if not access_token:
            try:
                from shared.auth.mcp_ada_auth import get_mcp_ada_access_token
                access_token = get_mcp_ada_access_token(user_id=mcp_user_id)

                if access_token:
                    # Cache in session for future use
                    tool_context.state[TOKEN_CACHE_KEY] = access_token
                    logging.info(f"Loaded MCP ADA token from file storage for {mcp_user_id}")
            except Exception as e:
                logging.warning(f"Failed to check file storage: {e}")

        if access_token:
            return {
                'authenticated': True,
                'user_id': user_id,
                'mcp_user_id': mcp_user_id,
                'server_url': server_url,
                'message': f'✅ Authenticated for MCP ADA (user: {mcp_user_id})',
                'token_available': True
            }
        else:
            logging.info(f"MCP ADA authentication required for user {mcp_user_id}. Please authenticate via frontend.")
            return {
                'authenticated': False,
                'user_id': user_id,
                'mcp_user_id': mcp_user_id,
                'server_url': server_url,
                'message': f'❌ Not authenticated for MCP ADA (user: {mcp_user_id}). Please run authentication first.',
                'token_available': False,
                'auth_url': 'http://localhost:8000/auth/mcp-ada/start'
            }

    except Exception as e:
        error_msg = f"❌ Error occurred during MCP authentication status check: {str(e)}"
        logging.error(error_msg)
        import traceback
        traceback.print_exc()
        return {
            'error': True,
            'authenticated': False,
            'message': error_msg
        }



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

    input_data = tool_context.state.get("ad_reports", {})

    try:
        input_data_json = json.dumps(input_data, ensure_ascii=False, indent=2)
        logging.info(f"[call_ds_agent] Successfully serialized input_data to JSON")
    except Exception as e:
        logging.error(f"[call_ds_agent] Failed to serialize input_data: {e}")
        input_data_json = "{}"

    question_with_data = f"""
  Question to answer: {question}

  Actual data to analyze previous question is already in the following JSON format:
  {input_data_json}

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