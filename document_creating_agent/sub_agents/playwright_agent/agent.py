"""playwright_agent: Playwright Agent creates the structure of the ad report."""

import os

from google.adk import Agent

from . import prompt

playwright_agent = Agent(
    name="playwright_agent",
    model=os.getenv("ROOT_AGENT_MODEL"),
    instruction=prompt.PLAYWRIGHT_PROMPT,
    output_key="playwright_output",
)
