"""playwright_agent: Playwright Agent creates the structure of the ad report."""

import os

from google.adk import Agent

from . import prompt

model = os.getenv("ROOT_AGENT_MODEL", "gemini-2.5-flash")

playwright_agent = Agent(
    name="playwright_agent",
    model=model,
    description="定例資料の基本構成・アウトラインを提案するエージェント",
    instruction=prompt.PLAYWRIGHT_PROMPT,
)
