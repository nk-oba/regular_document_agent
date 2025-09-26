"""playwright_agent: Playwright Agent creates the structure of the ad report."""

import os
from google.adk import Agent
from . import prompt

root_agent = Agent(
    name="playwright_agent",
    model=os.getenv("PLAYWRIGHT_AGENT_MODEL"),
    description="定例資料の基本構成・アウトラインを提案するエージェント",
    instruction=prompt.PLAYWRIGHT_PROMPT,
)
