import json
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
    get_tools,
    authenticate_mcp_server_tool,
    check_mcp_auth_status_tool,
    make_mcp_authenticated_request_tool
)
from .mcp_dynamic_tools import create_mcp_ada_dynamic_tools
from .sub_agents import ds_agent

EXECUTE_GET_AD_REPORT: str = "execute_get_ad_report"
EXECUTE_MCP_ADA_GET_CLIENT_LIST: str = "mcp_ada_get_client_list"
EXECUTE_MCP_ADA_GET_CLIENT_INFO: str = "mcp_ada_get_client_info"
EXECUTE_MCP_ADA_GET_REPORT: str = "mcp_ada_get_report"
EXECUTE_CALL_DS_AGENT: str = "call_ds_agent"

load_dotenv()

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logging.getLogger('mcp_client').setLevel(logging.DEBUG)
logging.getLogger('google.adk').setLevel(logging.DEBUG)
logging.getLogger('google.genai').setLevel(logging.DEBUG)
logging.getLogger('google_genai').setLevel(logging.DEBUG)

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
    print(tool_response)

    if tool.name == EXECUTE_GET_AD_REPORT:
        print(tool_response)
        if tool_response['status'] == "SUCCESS":
            tool_context.state["csv_report_output"] = tool_response['data']

    # Handle MCP tool responses with error checking
    if tool.name == EXECUTE_MCP_ADA_GET_CLIENT_LIST:
        # Check if response is an error message
        if isinstance(tool_response, str) and tool_response.startswith("❌"):
            logging.error(f"MCP tool error: {tool_response}")
            return tool_response
        try:
            json_data = json.loads(tool_response)
            tool_context.state["client_list"] = json_data
        except json.JSONDecodeError as e:
            logging.error(f"Failed to parse client_list response: {e}")
            return tool_response

    if tool.name == EXECUTE_MCP_ADA_GET_CLIENT_INFO:
        if isinstance(tool_response, str) and tool_response.startswith("❌"):
            logging.error(f"MCP tool error: {tool_response}")
            return tool_response
        try:
            json_data = json.loads(tool_response)
            tool_context.state["client_info"] = json_data
        except json.JSONDecodeError as e:
            logging.error(f"Failed to parse client_info response: {e}")
            return tool_response

    if tool.name == EXECUTE_MCP_ADA_GET_REPORT:
        if isinstance(tool_response, str) and tool_response.startswith("❌"):
            logging.error(f"MCP tool error: {tool_response}")
            return tool_response
        try:
            json_data = json.loads(tool_response)
            tool_context.state["ad_report"] = json_data
        except json.JSONDecodeError as e:
            logging.error(f"Failed to parse ad_report response: {e}")
            return tool_response
 
    return tool_response    


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
    # TEMPORARILY DISABLED: External MCP server has malformed tool schemas
    # Error: GenerateContentRequest.tools[0].function_declarations[2].parameters.properties[metrics].items: missing field
    # TODO: Fix the external MCP server schema before re-enabling
    try:
        mcp_tools = create_mcp_ada_dynamic_tools(tool_context)
        if mcp_tools:
            tools.extend(mcp_tools)
            logging.info(f"Added {len(mcp_tools)} MCP ADA dynamic tools to agent")

            # デバッグ: 各ツールのFunctionDeclarationを確認
            for tool in mcp_tools:
                if hasattr(tool, 'get_function_declarations'):
                    decls = tool.get_function_declarations()
                    for decl in decls:
                        logging.info(f"  MCP Tool FunctionDeclaration: {decl.name}")
    except Exception as e:
        logging.warning(f"Failed to add MCP ADA dynamic tools: {e}")

    # デバッグ: 最終的なツールリストを確認
    logging.info(f"Total tools in agent: {len(tools)}")
    for idx, tool in enumerate(tools):
        tool_type = type(tool).__name__
        tool_name = getattr(tool, 'name', 'unknown')
        logging.info(f"  Tool {idx+1}: {tool_type} - {tool_name}")

    return tools


_agent_tools = _get_agent_tools()

# デバッグ: 各ツールのFunctionDeclarationsを確認
logging.info("=== Checking all tool FunctionDeclarations before creating agent ===")
for idx, tool in enumerate(_agent_tools):
    if hasattr(tool, 'get_function_declarations'):
        try:
            decls = tool.get_function_declarations()
            logging.info(f"Tool {idx+1} ({type(tool).__name__}) declarations:")
            for decl in decls:
                logging.info(f"  - {decl.name}: {decl.description[:80] if decl.description else 'No description'}...")
        except Exception as e:
            logging.warning(f"Tool {idx+1} ({type(tool).__name__}) failed to get declarations: {e}")
    else:
        logging.info(f"Tool {idx+1} ({type(tool).__name__}) has no get_function_declarations method")

root_agent = LlmAgent(
    model=os.getenv("ROOT_AGENT_MODEL"),
    name="document_creating_agent",
    description=(
        "広告運用に関する報告資料を作成するエージェント"
    ),
    instruction=prompt.AD_REPORT_PROMPT,
    before_tool_callback=setup_before_to_call_tools,
    after_tool_callback=store_results_in_tool_context,
    # sub_agents=[
    #     ds_agent,
    # ],
    tools=_agent_tools,  # 関数を呼び出してツールリストを取得
    generate_content_config=types.GenerateContentConfig(temperature=0.01),
)

# デバッグ: Agentに登録されたツールを確認
logging.info("=== Agent initialized, checking registered tools ===")
if hasattr(root_agent, 'model') and hasattr(root_agent.model, 'tools'):
    logging.info(f"root_agent.model.tools count: {len(root_agent.model.tools)}")
    for idx, tool in enumerate(root_agent.model.tools, 1):
        logging.info(f"  {idx}. {type(tool).__name__}: {getattr(tool, 'name', 'unknown')}")
else:
    logging.warning("root_agent.model.tools not accessible")