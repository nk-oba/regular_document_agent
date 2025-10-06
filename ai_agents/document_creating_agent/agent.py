import logging
import os
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from google.adk.agents import LlmAgent
from google.adk.tools import BaseTool, load_artifacts, ToolContext
from google.genai import types

from . import prompt
from .tools import (
    call_ds_agent,
    call_playwright_agent,
    execute_get_ad_report,
    get_tools,
    authenticate_mcp_server_tool,
    check_mcp_auth_status_tool,
    make_mcp_authenticated_request_tool
)
from .mcp_dynamic_tools import create_mcp_ada_dynamic_tools
from .sub_agents import ds_agent

EXECUTE_GET_AD_REPORT: str = "execute_get_ad_report"
EXECUTE_GET_CSV_REPORT: str = "execute_get_csv_report"
EXECUTE_MCP_ADA_GET_REPORT: str = "mcp_ada_get_report"

load_dotenv()

def setup_before_to_call_tools(tool: BaseTool, args: Dict[str, Any], tool_context: ToolContext = None) -> None:
    """
    Setup before calling tools - ensure Google User ID is set in tool_context.state

    This function retrieves the Google User ID from the login session and sets it in
    tool_context.state for use in MCP ADA authentication and other tools.
    """
    if not tool_context:
        return

    # Get Google User ID from login session using session helper
    try:
        from .session_user_helper import get_user_id_from_session
        current_user_id = get_user_id_from_session(tool_context)
        
        if current_user_id and current_user_id != "default":
            tool_context.state["user_id"] = current_user_id
            logging.info(f"Set Google User ID from login session: {current_user_id}")
        else:
            logging.warning("No authenticated user found in login session")
            current_user_id = None
            
    except Exception as e:
        logging.error(f"Failed to get user ID from login session: {e}")
        current_user_id = None

    # Log tool execution
    if current_user_id:
        logging.info(f"Tool '{tool.name}' called for Google User ID: {current_user_id}")
    else:
        logging.warning(f"Tool '{tool.name}' called without Google User ID in session")

    # Optional: Log arguments for debugging (be careful with sensitive data)
    if logging.getLogger().isEnabledFor(logging.DEBUG):
        logging.debug(f"Tool arguments: {args}")

    # Note: Authentication checks are implemented within tool functions:
    # - authenticate_mcp_server_tool: Handles authentication flow
    # - check_mcp_auth_status_tool: Checks and returns auth status
    # - make_mcp_authenticated_request_tool: Validates token before request
    # This avoids duplication and keeps authentication logic in one place.

def store_results_in_tool_context(
    tool: BaseTool, args: Dict[str, Any], tool_context: ToolContext, tool_response: Dict
) -> Optional[Dict]:
    """Store the results in the tool context."""
    if tool.name == EXECUTE_GET_AD_REPORT:
        print(tool_response)
        if tool_response['status'] == "SUCCESS":
            tool_context.state["csv_report_output"] = tool_response['data']
    elif tool.name == EXECUTE_MCP_ADA_GET_REPORT:
        print(tool_response)
        # if tool_response['status'] == "SUCCESS":
        #     tool_context.state["mcp_ada_report_output"] = tool_response['data']
    return tool_response    


logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logging.getLogger('mcp_client').setLevel(logging.DEBUG)
logging.getLogger('google.adk').setLevel(logging.DEBUG)

def _get_agent_tools(tool_context: Optional[ToolContext] = None):
    """
    エージェントのツールリストを動的に生成

    Args:
        tool_context: ADK tool context（MCP動的ツール生成に使用）

    Returns:
        List: エージェントツールのリスト
    """
    tools = [
        load_artifacts,
        call_ds_agent,
        # execute_get_ad_report,
        # MCP ADA authentication tools
        # authenticate_mcp_server_tool,
        # check_mcp_auth_status_tool,
        # make_mcp_authenticated_request_tool,
    ]

    # MCP ADA動的ツールを追加（OAuth2自動更新対応）
    try:
        mcp_tools = create_mcp_ada_dynamic_tools(tool_context)
        if mcp_tools:
            tools.extend(mcp_tools)
            logging.info(f"Added {len(mcp_tools)} MCP ADA dynamic tools to agent")
    except Exception as e:
        logging.warning(f"Failed to add MCP ADA dynamic tools: {e}")

    return tools


root_agent = LlmAgent(
    model=os.getenv("ROOT_AGENT_MODEL"),
    name="document_creating_agent",
    description=(
        "広告運用に関する報告資料を作成するエージェント"
    ),
    # instruction=prompt.AD_REPORT_PROMPT,
    before_tool_callback=setup_before_to_call_tools,
    after_tool_callback=store_results_in_tool_context,
    # sub_agents=[
    #     ds_agent,
    # ],
    tools=_get_agent_tools(),  # 関数を呼び出してツールリストを取得
    generate_content_config=types.GenerateContentConfig(temperature=0.01),
)