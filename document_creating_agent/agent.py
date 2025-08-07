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


load_dotenv()

logging.basicConfig(level=logging.DEBUG)

ad_agency = LlmAgent(
    model=os.getenv("ROOT_AGENT_MODEL"),
    name="document_creating_agent",
    description=(
        "広告運用に関する報告資料を作成するエージェント"
    ),
    instruction=prompt.AD_REPORT_PROMPT,
    sub_agents=[
        ad_analyzer_agent,
        playwright_agent,
        slide_agent,
    ],
    tools=[
        load_artifacts, 
        # *get_tools(),
    ],
    generate_content_config=types.GenerateContentConfig(temperature=0.01),
)

root_agent = ad_agency