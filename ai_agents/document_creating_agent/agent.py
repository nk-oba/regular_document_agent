import logging
import os
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from google.adk.agents import LlmAgent
from google.adk.tools import BaseTool, load_artifacts, ToolContext
from google.genai import types

from . import prompt
from .tools import call_ds_agent, call_playwright_agent, execute_get_ad_report, get_tools
from .sub_agents import ds_agent

EXECUTE_GET_AD_REPORT: str = "execute_get_ad_report"
EXECUTE_GET_CSV_REPORT: str = "execute_get_csv_report"

load_dotenv()

def setup_before_to_call_tools(tool: BaseTool, args: Dict[str, Any], tool_context: ToolContext = None) -> None:
    """Setup the tool."""
    # TODO MCPサーバーの認証を行う

def store_results_in_tool_context(
    tool: BaseTool, args: Dict[str, Any], tool_context: ToolContext, tool_response: Dict
) -> Optional[Dict]:
    """Store the results in the tool context."""
    if tool.name == EXECUTE_GET_CSV_REPORT:
        print(tool_response)
        if tool_response['status'] == "SUCCESS":
            tool_context.state["csv_report_output"] = tool_response['data']
    
    return tool_response    


logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logging.getLogger('mcp_client').setLevel(logging.DEBUG)
logging.getLogger('google.adk').setLevel(logging.DEBUG)

root_agent = LlmAgent(
    model=os.getenv("ROOT_AGENT_MODEL"),
    name="document_creating_agent",
    description=(
        "広告運用に関する報告資料を作成するエージェント"
    ),
    # instruction=prompt.AD_REPORT_PROMPT,
    # TODO: Re-enable tool hooks when ADK supports them
    before_tool_callback=setup_before_to_call_tools,
    after_tool_callback=store_results_in_tool_context,
    sub_agents=[
        ds_agent,
    ],
    tools=[
        call_playwright_agent,
        # call_ds_agent,
        load_artifacts,
        execute_get_ad_report,
    ],
    generate_content_config=types.GenerateContentConfig(temperature=0.01),
)