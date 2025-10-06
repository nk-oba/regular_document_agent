import os
from google.adk import Agent

from . import prompt
from .tools import get_tools

root_agent = Agent(
    name="slide_agent",
    model=os.getenv("SLIDE_AGENT_MODEL"),
    instruction=prompt.SLIDE_PROMPT,
    tools=[
        *get_tools(),
    ],
)
