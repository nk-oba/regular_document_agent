"""ad_analyzer_agent: Ad Analyzer Agent analyzes the ad data."""

import os

from google.adk import Agent

from . import prompt
from .tools import get_tools

ad_analyzer_agent = Agent(
    name="ad_analyzer_agent",
    model=os.getenv("ROOT_AGENT_MODEL"),
    instruction=prompt.AD_ANALYZER_PROMPT,
    tools=get_tools(),
    output_key="ad_analyzer_output",
)
