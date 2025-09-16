import logging
import os

from dotenv import load_dotenv

from google.genai import types
from google.adk.agents import LlmAgent
from google.adk.tools import load_artifacts

from .import prompt
from .sub_agents.ad_analyzer_agent import ad_analyzer_agent
from .sub_agents.playwright_agent import playwright_agent
from .sub_agents.slide_agent import slide_agent
from .tools import get_tools

# state keys
STATE_INITIAL = "initial_info"
STATE_AD_DATA = "ad_data"
STATE_PLAYWRIGHT_DOC = "current_doc"

load_dotenv()

# MCP ADAデバッグログを有効化
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# MCP関連のログを特に詳細に設定
logging.getLogger('mcp_client').setLevel(logging.DEBUG)
logging.getLogger('google.adk').setLevel(logging.DEBUG)

tools = [load_artifacts]
try:
    mcp_tools = get_tools()
    tools.extend(mcp_tools)
    logging.info(f"Successfully loaded {len(mcp_tools)} MCP tools")
except Exception as e:
    logging.error(f"Failed to load MCP tools: {str(e)}")

sub_agents = []
# try:
#     sub_agents.append(ad_analyzer_agent)
#     logging.info("Successfully loaded ad_analyzer_agent")
# except Exception as e:
#     logging.error(f"Failed to load ad_analyzer_agent: {str(e)}")

# try:
#     sub_agents.append(playwright_agent)
#     logging.info("Successfully loaded playwright_agent")
# except Exception as e:
#     logging.error(f"Failed to load playwright_agent: {str(e)}")

# slide_agentはコメントアウト
# try:
#     sub_agents.append(slide_agent)
#     logging.info("Successfully loaded slide_agent")
# except Exception as e:
#     logging.error(f"Failed to load slide_agent: {str(e)}")

# モデル名を安全に取得
model = os.getenv("ROOT_AGENT_MODEL")
if not model:
    logging.warning("ROOT_AGENT_MODEL not found, using default model")
    model = "gemini-1.5-flash"

ad_agency = LlmAgent(
    model=model,
    name="document_creating_agent",
    description=(
        "広告運用に関する報告資料を作成するエージェント"
    ),
    instruction=prompt.AD_REPORT_PROMPT,
    sub_agents=sub_agents,
    tools=tools,
    generate_content_config=types.GenerateContentConfig(temperature=0.01),
    output_key=STATE_INITIAL,
)

root_agent = ad_agency